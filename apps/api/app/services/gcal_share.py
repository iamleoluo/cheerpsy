"""心理師日曆的佈建與分享同步（docs/gcal-sync-plan.md §1、§2.2、§2.3-6）。

規則（沙盒 2026-11-16 實測定案）：
- 每位心理師一本日曆，診所帳號擁有；沒有總表。
- 分享名單 =（在職且有 Gmail 的心理師本人）∪ 行政名單 − 擁有者，一律以 reader 分享。
- 同一信箱同時是心理師與行政：聯集去重，只有一筆 rule；從任一邊移除時，另一邊仍在就不刪。
- 只寫「差集」：Google 的 acl.insert 每新增一筆就寄一封分享信，重複 insert 會重複打擾對方。
- acl.list 會列出擁有者（role=owner）：擁有者不納入比較、永遠不刪。
- 離職／取消分享：移除心理師本人的 rule、日曆保留並凍結（is_active=false），行政名單仍可看。
- 刪除先於新增：更換信箱時先取消舊的再分享新的。
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.gcal import ClinicSettings, GoogleCalendar, GoogleOAuthConnection
from app.models.user import User
from app.services import gcal_client
from app.services.gcal_client import CalendarApiError, CalendarClient, GcalNotConnected

logger = logging.getLogger("cheerpsy.gcal")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# 官方建議：短時間不要建立超過 60 個日曆。診所只有十幾位心理師，抓 50／小時當保險絲。
MAX_CALENDARS_PER_HOUR = 50
_RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded",
                 "calendarUsageLimitsExceeded"}


class GcalThrottled(Exception):
    pass


def normalize_email(value: str | None) -> str | None:
    v = (value or "").strip().lower()
    return v or None


def calendar_summary(therapist: User) -> str:
    return f"{therapist.name} · Cheerpsy"


def staff_emails(db: Session) -> list[str]:
    row = db.get(ClinicSettings, 1)
    return list(row.staff_share_emails or []) if row else []


def owner_email(db: Session) -> str | None:
    conn = db.get(GoogleOAuthConnection, 1)
    return normalize_email(conn.google_email) if conn else None


def target_emails(therapist: User, row: GoogleCalendar, staff: list[str]) -> set[str]:
    """這本日曆應有的分享名單（尚未扣掉擁有者）：行政名單，加上在職、未被取消分享的心理師本人。"""
    want = {e for e in (normalize_email(s) for s in staff) if e}
    mine = normalize_email(therapist.gcal_share_email)
    if mine and therapist.is_active and row.is_active:
        want.add(mine)
    return want


@dataclass
class AclResult:
    final: list[str]  # 同步後 Google 上的分享名單（不含擁有者）
    owners: set[str]
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def sync_acl(client: CalendarClient, calendar_id: str, want: set[str], known_owner: str | None) -> AclResult:
    rules = client.list_acl(calendar_id)
    owners = {r.value for r in rules if r.role == "owner"}
    if known_owner:
        owners.add(known_owner)
    want = want - owners  # 擁有者本來就看得到，不分享、也不算多餘

    have = {r.value: r for r in rules if r.role != "owner" and r.scope_type == "user"}
    # 非「個別使用者」的 rule（公開、整個網域、群組）不在我們的分享設計內；日曆含個案行程，一律移除
    stray = [r for r in rules if r.role != "owner" and r.scope_type != "user"]

    result = AclResult(final=[], owners=owners)
    for email, rule in have.items():  # 先刪：更換信箱時舊的要先取消
        if email not in want:
            _delete_rule(client, calendar_id, rule.rule_id)
            result.removed.append(email)
    for rule in stray:
        _delete_rule(client, calendar_id, rule.rule_id)
        result.removed.append(rule.scope_type)
    for email in sorted(want & set(have)):
        if have[email].role != "reader":
            client.patch_acl_role(calendar_id, have[email].rule_id, "reader")
    for email in sorted(want - set(have)):
        client.insert_acl(calendar_id, email, "reader", send_notifications=True)
        result.added.append(email)
    result.final = sorted(want)
    return result


def _delete_rule(client: CalendarClient, calendar_id: str, rule_id: str) -> None:
    try:
        client.delete_acl(calendar_id, rule_id)
    except CalendarApiError as e:
        if e.status not in (404, 410):  # 已經不存在就算成功
            raise


def describe_error(e: CalendarApiError) -> str:
    if e.status in (404, 410):
        return "Google 上找不到這本日曆（可能被手動刪除），請按「建立並分享」重建"
    if e.status == 429 or (e.status == 403 and e.reason in _RATE_REASONS):
        return "Google 流量限制，請稍後再試"
    if e.status in (401, 403):
        return "Google 拒絕這個操作（授權或權限不足），請管理員檢查連線"
    if e.status == 0:
        return "無法連線到 Google，請稍後再試"
    return f"Google 回應錯誤（HTTP {e.status}）"


def _therapist_status(therapist: User, row: GoogleCalendar, result: AclResult) -> str:
    mine = normalize_email(therapist.gcal_share_email)
    if not therapist.is_active or not row.is_active:
        return "unshared"
    if not mine:
        return "not_shared"
    if mine in result.owners:
        return "owner"
    return "invited" if mine in result.final else "not_shared"


def sync_calendar(db: Session, client: CalendarClient, row: GoogleCalendar, therapist: User) -> bool:
    """把一本日曆的名稱與分享名單同步到 Google。失敗不丟例外，記錄在 row 上並回傳 False。呼叫端負責 commit。"""
    try:
        if row.summary != calendar_summary(therapist):
            client.rename_calendar(row.google_calendar_id, calendar_summary(therapist))
            row.summary = calendar_summary(therapist)
        want = target_emails(therapist, row, staff_emails(db))
        res = sync_acl(client, row.google_calendar_id, want, owner_email(db))
    except CalendarApiError as e:
        row.share_status = "error"
        row.last_share_error = describe_error(e)
        if e.status in (404, 410):
            row.is_missing = True
        logger.warning("gcal share sync failed (therapist_id=%s): HTTP %s %s", therapist.id, e.status, e.reason)
        return False
    row.shared_emails = res.final
    row.share_status = _therapist_status(therapist, row, res)
    row.last_share_error = None
    row.is_missing = False
    gcal_client.mark_success(db)
    return True


def provision(db: Session, client: CalendarClient, therapist: User) -> GoogleCalendar:
    """建立（或重建被刪掉的）日曆，並依聯集分享。可重複呼叫：已存在就只做分享同步。

    建立日曆後先 commit：就算後面分享失敗，日曆 id 也不會遺失（也不會因重試而建出第二本）。"""
    row = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == therapist.id).first()
    if row is None or row.is_missing:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = db.query(GoogleCalendar).filter(GoogleCalendar.created_at >= since).count()
        if recent >= MAX_CALENDARS_PER_HOUR:
            raise GcalThrottled(
                f"最近一小時已建立 {recent} 本日曆。Google 建議短時間內不要建立超過 60 本，請稍後再試")
        info = client.create_calendar(calendar_summary(therapist), gcal_client.TIME_ZONE, gcal_client.CALENDAR_DESCRIPTION)
        if row is None:
            row = GoogleCalendar(therapist_id=therapist.id, google_calendar_id=info.id, summary=info.summary)
            db.add(row)
        else:
            row.google_calendar_id = info.id
            row.summary = info.summary
            row.created_at = datetime.now(timezone.utc)
        row.is_missing = False
        row.share_status = "not_shared"
        row.last_share_error = None
        row.shared_emails = []
        db.commit()
    row.is_active = True
    sync_calendar(db, client, row, therapist)
    db.commit()
    return row


def unshare(db: Session, client: CalendarClient, row: GoogleCalendar, therapist: User) -> GoogleCalendar:
    """取消心理師本人的分享並凍結日曆（日曆與事件保留）。行政名單的分享不受影響。可重複呼叫。"""
    row.is_active = False
    sync_calendar(db, client, row, therapist)
    db.commit()
    return row


def resend_invite(db: Session, client: CalendarClient, row: GoogleCalendar, therapist: User) -> GoogleCalendar:
    """重送分享信：先刪掉舊的 rule 再建（sendNotifications=true）。只限心理師本人的信箱。"""
    mine = normalize_email(therapist.gcal_share_email)
    try:
        for r in client.list_acl(row.google_calendar_id):
            if r.value == mine and r.role != "owner":
                _delete_rule(client, row.google_calendar_id, r.rule_id)
        client.insert_acl(row.google_calendar_id, mine, "reader", send_notifications=True)
    except CalendarApiError as e:
        row.share_status = "error"
        row.last_share_error = describe_error(e)
        if e.status in (404, 410):
            row.is_missing = True
        db.commit()
        return row
    sync_calendar(db, client, row, therapist)
    db.commit()
    return row


def sync_all(db: Session, client: CalendarClient) -> tuple[int, int]:
    """行政名單變動後，對所有日曆（含凍結的）重算分享名單。回傳 (成功, 失敗) 本數；單本失敗不影響其他本。"""
    ok = failed = 0
    for row in db.query(GoogleCalendar).order_by(GoogleCalendar.id).all():
        if row.is_missing:
            continue  # 日曆已不存在，沒有東西可同步
        therapist = db.get(User, row.therapist_id)
        if therapist is None:
            continue
        if sync_calendar(db, client, row, therapist):
            ok += 1
        else:
            failed += 1
        db.commit()
    return ok, failed


def auto_provision_best_effort(db: Session, therapist: User) -> GoogleCalendar | None:
    """心理師填了（或改了）分享信箱後，自動建立日曆並分享。回傳新佈建／重建的日曆列；沒動作或失敗回 None。

    只在「在職、有信箱、尚無可用日曆（沒有或已被刪）」時動作；已凍結（取消分享）的日曆不會被自動恢復。
    永遠不丟例外、不回滾呼叫端已 commit 的存檔：Google 未連結就什麼都不做（手動「建立並分享」補救），
    分享階段失敗則記在日曆列上。呼叫端須在存檔 commit 之後才呼叫。"""
    try:
        if therapist.role != "therapist" or not therapist.is_active or not normalize_email(therapist.gcal_share_email):
            return None
        # 鎖心理師列，避免與手動「建立並分享」併發建出兩本日曆
        locked = db.query(User).filter(User.id == therapist.id).with_for_update().first()
        if locked is None:
            return None
        row = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == locked.id).first()
        if row is not None and not row.is_missing:
            db.rollback()  # 放掉鎖
            return None
        try:
            client = gcal_client.get_calendar_client(db)
        except GcalNotConnected:
            db.rollback()
            return None
        try:
            cal = provision(db, client, locked)
        except (GcalThrottled, CalendarApiError) as e:
            db.rollback()
            logger.warning("gcal auto-provision skipped (therapist_id=%s): %s", therapist.id, type(e).__name__)
            return None
        return cal
    except Exception:  # noqa: BLE001 — 存檔已完成，這裡不能讓請求失敗
        logger.exception("gcal auto-provision failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def sync_for_user_best_effort(db: Session, user: User) -> None:
    """心理師在名冊被停用（離職）或恢復時，讓日曆的凍結狀態與分享跟上。

    不可讓名冊操作因 Google 而失敗：任何錯誤都只記在日曆列上（畫面會顯示「同步失敗」，
    管理員可按「取消分享」重試）。沒有日曆就什麼都不做。"""
    row = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == user.id).first()
    if row is None:
        return
    row.is_active = bool(user.is_active)
    try:
        client = gcal_client.get_calendar_client(db)
    except GcalNotConnected as e:
        row.share_status = "error"
        row.last_share_error = f"尚未同步到 Google：{e.message}"
        db.commit()
        return
    except Exception:  # noqa: BLE001 — 名冊操作不能因這裡失敗
        logger.exception("gcal best-effort sync: client setup failed")
        db.rollback()
        return
    try:
        sync_calendar(db, client, row, user)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("gcal best-effort sync failed")
        db.rollback()
