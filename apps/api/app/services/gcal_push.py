"""Outbox 工作者的處理邏輯：把預約推成 Google 事件（docs/gcal-sync-plan.md §2.3）。

- 領取：`FOR UPDATE SKIP LOCKED` 取一批到期的 pending／retry，標成 running 後立刻 commit（不在交易裡等 Google），
  所以預約 API 入列時不會被卡住；多個工作者也不會搶同一筆。
- 執行前重讀預約現況：該做 upsert 還是 delete 由「現在」的預約狀態決定，不由入列當時的 job_type 決定。
- 冪等：事件 id 由預約 id 決定；payload_hash 沒變就不打 API。
- 錯誤：429／5xx／網路 → 指數退避重試，用盡次數標成 failed；invalid_grant → 連線標 token_invalid、全部 blocked；
  日曆／連線條件不足 → blocked（補齊後可「重試」）。
- 完成時只在版本沒變的情況下標 done：處理期間若預約又異動（入列把版本加一），這一列保持待處理。
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models.appointment import Appointment
from app.models.gcal import AppointmentGoogleEvent, ClinicSettings, GoogleCalendar
from app.services import gcal_client, gcal_titles
from app.services.gcal_client import CalendarApiError, CalendarClient, GcalNotConnected

logger = logging.getLogger("cheerpsy.gcal")

MAX_ATTEMPTS = 10
BACKOFF_BASE_SECONDS = 2
BACKOFF_CAP_SECONDS = 900
STALE_RUNNING_MINUTES = 10  # 工作者當掉時留下的 running，超過這個時間收回重跑
BATCH_SIZE = 20
_RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded",
                 "calendarUsageLimitsExceeded"}


@dataclass
class Outcome:
    kind: str  # done | blocked | retry | failed
    message: str | None = None


def backoff_seconds(attempts: int) -> float:
    """attempts 是「已失敗次數」：2、4、8…秒，加抖動，上限 15 分鐘。"""
    base = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)))
    return base + random.uniform(0, min(base, 5))


def _retryable(e: CalendarApiError) -> bool:
    if e.status in (0, 401, 408, 429) or e.status >= 500:
        return True
    return e.status == 403 and e.reason in _RATE_REASONS


def describe(e: CalendarApiError) -> str:
    if e.status == 0:
        return "無法連線到 Google"
    if _retryable(e):
        return f"Google 暫時無法處理（HTTP {e.status}），稍後自動重試"
    if e.status == 403:
        return "Google 拒絕這個操作（權限不足），請管理員檢查連線"
    return f"Google 回應錯誤（HTTP {e.status}）"


# ---------------------------------------------------------------------------
# 單一工作
# ---------------------------------------------------------------------------
def _title_format(db: Session) -> str:
    row = db.get(ClinicSettings, 1)
    return row.event_title_format if row else "type_room_name"


def _delete_remote(client: CalendarClient, calendar_id: str, event_id: str) -> None:
    try:
        client.delete_event(calendar_id, event_id)
    except CalendarApiError as e:
        if e.status not in (404, 410):  # 已經不在了就算成功
            raise


def _push_remote(client: CalendarClient, calendar_id: str, event_id: str, body: dict, known: bool) -> None:
    """已有對應就先 update；沒有就 insert。對方說不存在／已存在就改走另一條（事件被手動刪或曾刪除過）。"""
    if known:
        try:
            client.update_event(calendar_id, event_id, body)
            return
        except CalendarApiError as e:
            if e.status != 404:
                raise
    try:
        client.insert_event(calendar_id, body)
    except CalendarApiError as e:
        if e.status != 409:
            raise
        client.update_event(calendar_id, event_id, body)  # 曾刪除的同 id 事件：update 即可復活


def _plan_name(db: Session, a: Appointment) -> str | None:
    """機構案的方案名稱（給心理師的提醒用）；只取名稱。"""
    if not a.plan_id:
        return None
    return db.execute(text("SELECT name FROM institution_plans WHERE id = :i"), {"i": a.plan_id}).scalar()


def note_sections(db: Session, a: Appointment) -> list[tuple[str, str]]:
    """放進事件描述的備註分段 [(標題, 內文)]。

    目前預約上沒有備註欄位（appointments 無 notes），所以是空的。PR D 的「備註給心理師」做好後，在這裡加一段
    ("備註給心理師", 內文)；內文變動時事件內容 hash 會變、並要在寫備註的路徑入列（見計畫書 PR C 實作備註）。"""
    return []


def process(db: Session, client: CalendarClient, appointment_id: int) -> Outcome:
    """讓 Google 與這筆預約的現況一致。呼叫端負責 commit／rollback。"""
    a = (db.query(Appointment)
         .options(joinedload(Appointment.room), joinedload(Appointment.case), joinedload(Appointment.couple_case))
         .filter(Appointment.id == appointment_id).first())
    mapping = db.get(AppointmentGoogleEvent, appointment_id)
    if a is None:  # 預約被刪除：有對應事件就從 Google 刪掉
        if mapping is not None and mapping.last_status == "pushed":
            old = db.query(GoogleCalendar).filter(GoogleCalendar.google_calendar_id == mapping.google_calendar_id).first()
            if old is not None and not old.is_active:
                return Outcome("done", "日曆已凍結（心理師離職），不再更新")
            _delete_remote(client, mapping.google_calendar_id, mapping.google_event_id)
            mapping.last_status = "deleted"
            mapping.payload_hash = ""
            mapping.last_pushed_at = datetime.now(timezone.utc)
        return Outcome("done", "預約已不存在")

    cal = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == a.therapist_id).first()
    wanted = a.status in ("booked", "executed") and a.time_range is not None

    # 事件目前所在的日曆與「該在的日曆」不同（改派心理師），或預約不該再出現：先從舊日曆移除。
    # 凍結（離職）的日曆只做這種「不屬於他的場次」清理，其餘一律不動。
    if mapping is not None and mapping.last_status == "pushed":
        stays = wanted and cal is not None and mapping.google_calendar_id == cal.google_calendar_id
        if not stays:
            old = db.query(GoogleCalendar).filter(GoogleCalendar.google_calendar_id == mapping.google_calendar_id).first()
            frozen_own = old is not None and not old.is_active and old.therapist_id == a.therapist_id
            if frozen_own:
                return Outcome("done", "日曆已凍結（心理師離職），不再更新")
            _delete_remote(client, mapping.google_calendar_id, mapping.google_event_id)
            mapping.last_status = "deleted"
            mapping.payload_hash = ""
            mapping.last_pushed_at = datetime.now(timezone.utc)
    if not wanted:
        return Outcome("done")

    if cal is None:
        return Outcome("blocked", "這位心理師還沒有 Google 日曆，請到「日曆分享」建立並分享")
    if cal.is_missing:
        return Outcome("blocked", "這位心理師的日曆在 Google 上找不到，請重新建立")
    if not cal.is_active:
        return Outcome("done", "日曆已凍結（心理師離職），不再更新")

    body = gcal_titles.event_body(a, _title_format(db), note_sections(db, a), plan_name=_plan_name(db, a))
    new_hash = gcal_titles.payload_hash(cal.google_calendar_id, body)
    same_calendar = mapping is not None and mapping.google_calendar_id == cal.google_calendar_id
    if same_calendar and mapping.last_status == "pushed" and mapping.payload_hash == new_hash:
        return Outcome("done")  # 內容沒變，不打 API

    known = same_calendar and mapping.last_status == "pushed"
    try:
        _push_remote(client, cal.google_calendar_id, body["id"], body, known)
    except CalendarApiError as e:
        if e.status == 404:  # insert 回 404：日曆本身不見了
            cal.is_missing = True
            cal.share_status = "error"
            cal.last_share_error = "Google 上找不到這本日曆（可能被手動刪除），請按「建立並分享」重建"
            return Outcome("blocked", "這位心理師的日曆在 Google 上找不到，請重新建立")
        raise
    if mapping is None:
        mapping = AppointmentGoogleEvent(appointment_id=a.id)
        db.add(mapping)
    mapping.google_calendar_id = cal.google_calendar_id
    mapping.google_event_id = body["id"]
    mapping.payload_hash = new_hash
    mapping.last_status = "pushed"
    mapping.last_pushed_at = datetime.now(timezone.utc)
    return Outcome("done")


# ---------------------------------------------------------------------------
# 領取與結案
# ---------------------------------------------------------------------------
def _claim(db: Session, now: datetime, limit: int) -> list[tuple[int, int, int, int]]:
    """回傳 [(outbox id, appointment_id, version, 已嘗試次數)]。"""
    db.execute(text(
        "UPDATE gcal_outbox SET status = 'retry', claimed_at = NULL, updated_at = now() "
        "WHERE status = 'running' AND claimed_at < :stale"), {"stale": now - timedelta(minutes=STALE_RUNNING_MINUTES)})
    rows = db.execute(text(
        "SELECT id, appointment_id, version, attempts FROM gcal_outbox "
        "WHERE status IN ('pending', 'retry') AND next_attempt_at <= :now "
        "ORDER BY next_attempt_at, id LIMIT :n FOR UPDATE SKIP LOCKED"), {"now": now, "n": limit}).all()
    if rows:
        db.execute(text("UPDATE gcal_outbox SET status = 'running', claimed_at = :now, updated_at = now() "
                        "WHERE id = ANY(:ids)"), {"now": now, "ids": [r[0] for r in rows]})
    db.commit()
    return [tuple(r) for r in rows]


def _finish(db: Session, job_id: int, version: int, status: str, attempts: int, error: str | None,
            next_at: datetime | None = None) -> None:
    db.execute(text(
        "UPDATE gcal_outbox SET status = :s, attempts = :att, last_error = :err, claimed_at = NULL, updated_at = now(), "
        "next_attempt_at = COALESCE(:next, next_attempt_at), "
        "finished_at = CASE WHEN :s IN ('done', 'failed') THEN now() ELSE NULL END "
        "WHERE id = :id AND version = :v AND status = 'running'"),
        {"s": status, "att": attempts, "err": error, "next": next_at, "id": job_id, "v": version})
    db.commit()


def block_everything(db: Session, message: str) -> int:
    """授權失效等：所有未完成的工作改成 blocked，重新連結後按「重試」。"""
    n = db.execute(text(
        "UPDATE gcal_outbox SET status = 'blocked', last_error = :m, claimed_at = NULL, updated_at = now() "
        "WHERE status IN ('pending', 'retry', 'running')"), {"m": message}).rowcount
    db.commit()
    return n


def run_once(session_factory=SessionLocal, client_factory=None, now: datetime | None = None,
             batch: int = BATCH_SIZE) -> int:
    """處理一批到期的工作。回傳處理的筆數（0＝沒有事做）。不丟例外。"""
    client_factory = client_factory or gcal_client.get_calendar_client
    now = now or datetime.now(timezone.utc)
    db = session_factory()
    try:
        # 沒有可用連線時不領取，免得白白消耗重試次數
        try:
            client = client_factory(db)
        except GcalNotConnected as e:
            if not e.transient:
                n = block_everything(db, e.message)
                if n:
                    logger.warning("gcal worker: %s job(s) blocked: %s", n, e.message)
            return 0
        jobs = _claim(db, now, batch)
        for job_id, appointment_id, version, attempts in jobs:
            _run_job(db, client, job_id, appointment_id, version, attempts, now)
        return len(jobs)
    except Exception:  # noqa: BLE001 — 工作者不可因單次異常結束
        logger.exception("gcal worker: batch failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0
    finally:
        db.close()


def _run_job(db: Session, client: CalendarClient, job_id: int, appointment_id: int, version: int, attempts: int,
             now: datetime) -> None:
    try:
        outcome = process(db, client, appointment_id)
        db.commit()
        if outcome.kind == "done":
            gcal_client.mark_success(db)
            db.commit()
    except CalendarApiError as e:
        db.rollback()
        attempts += 1
        if _retryable(e) and attempts < MAX_ATTEMPTS:
            outcome = Outcome("retry", describe(e))
            wait = backoff_seconds(attempts)
        else:
            outcome = Outcome("failed", describe(e))
            wait = 0
        logger.warning("gcal push failed (appointment_id=%s): HTTP %s %s -> %s", appointment_id, e.status, e.reason, outcome.kind)
        _finish(db, job_id, version, outcome.kind, attempts, outcome.message, now + timedelta(seconds=wait))
        return
    except GcalNotConnected as e:  # 保險：處理中授權失效
        db.rollback()
        _finish(db, job_id, version, "blocked", attempts, e.message)
        return
    except Exception:  # noqa: BLE001 — 程式錯誤：不要卡住整批，記下來並重試
        db.rollback()
        logger.exception("gcal push crashed (appointment_id=%s)", appointment_id)
        attempts += 1
        kind = "failed" if attempts >= MAX_ATTEMPTS else "retry"
        _finish(db, job_id, version, kind, attempts, "內部錯誤，請查看伺服器日誌",
                now + timedelta(seconds=backoff_seconds(attempts)))
        return
    if outcome.kind == "blocked":
        _finish(db, job_id, version, "blocked", attempts, outcome.message)
    else:
        _finish(db, job_id, version, "done", attempts, outcome.message)
