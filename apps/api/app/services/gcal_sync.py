"""Outbox 的管理操作：健康狀態、重試、單一心理師入列、全部重新同步（docs/gcal-sync-plan.md §2.3-7）。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.gcal import ClinicSettings
from app.models.gcal_hooks import enqueue_appointments

RESYNC_STEP_SECONDS = 0.3  # 全部重新同步：每筆錯開，避免一次打爆單一日曆
RESYNC_MAX_APPOINTMENTS = 5000


def counts(db: Session) -> dict[str, int]:
    rows = db.execute(text("SELECT status, count(*) FROM gcal_outbox GROUP BY status")).all()
    out = {s: 0 for s in ("pending", "running", "retry", "blocked", "done", "failed")}
    out.update({r[0]: int(r[1]) for r in rows})
    return out


def problem_jobs(db: Session, limit: int = 50) -> list[dict]:
    """失敗／被擋住的工作，給 /gcal 顯示。只含預約編號、心理師、時間與原因，沒有個案資料。"""
    rows = db.execute(text("""
        SELECT o.id, o.status, o.attempts, o.last_error, o.updated_at, a.id AS appointment_id,
               a.appointment_number, u.name AS therapist_name, lower(a.time_range) AS starts_at
        FROM gcal_outbox o
        JOIN appointments a ON a.id = o.appointment_id
        JOIN users u ON u.id = a.therapist_id
        WHERE o.status IN ('failed', 'blocked')
        ORDER BY o.status, o.updated_at DESC, o.id LIMIT :n"""), {"n": limit}).mappings().all()
    return [dict(r) for r in rows]


def requeue(db: Session, statuses=("failed", "blocked"), therapist_id: int | None = None) -> int:
    """把失敗／被擋住的工作重新排入（次數歸零）。可只重排某位心理師的。呼叫端負責 commit。"""
    sql = ("UPDATE gcal_outbox o SET status = 'pending', attempts = 0, next_attempt_at = now(), last_error = NULL, "
           "claimed_at = NULL, finished_at = NULL, version = o.version + 1, updated_at = now() "
           "WHERE o.status = ANY(:st)")
    params: dict = {"st": list(statuses)}
    if therapist_id is not None:
        sql += " AND o.appointment_id IN (SELECT id FROM appointments WHERE therapist_id = :t)"
        params["t"] = therapist_id
    return db.execute(text(sql), params).rowcount


def _window(db: Session) -> tuple[datetime, datetime]:
    s = db.get(ClinicSettings, 1)
    back = s.resync_lookback_days if s else 30
    ahead = s.resync_lookahead_days if s else 180
    now = datetime.now(timezone.utc)
    return now - timedelta(days=back), now + timedelta(days=ahead)


def enqueue_therapist_window(db: Session, therapist_id: int) -> int:
    """日曆剛建好／重新啟用：把這位心理師在同步區間內的預約排入（含先前因「沒有日曆」被擋的）。"""
    lo, hi = _window(db)
    ids = db.execute(text(
        "SELECT id FROM appointments WHERE therapist_id = :t AND status IN ('booked', 'executed') "
        "AND time_range && tstzrange(:lo, :hi)"), {"t": therapist_id, "lo": lo, "hi": hi}).scalars().all()
    return enqueue_appointments(db.connection(), ids, step_seconds=0.1)


def resync_all(db: Session) -> dict:
    """全部重新同步：區間內所有 booked／executed 預約排入 upsert（並清掉雜湊，強制覆寫 Google 上被改過的內容）；
    已有對應事件、但預約已取消／未到的排入 delete。回傳各項數量。呼叫端負責 commit。"""
    lo, hi = _window(db)
    upsert_ids = db.execute(text(
        "SELECT id FROM appointments WHERE status IN ('booked', 'executed') AND time_range && tstzrange(:lo, :hi) "
        "ORDER BY id LIMIT :n"), {"lo": lo, "hi": hi, "n": RESYNC_MAX_APPOINTMENTS}).scalars().all()
    delete_ids = db.execute(text(
        "SELECT e.appointment_id FROM appointment_google_events e JOIN appointments a ON a.id = e.appointment_id "
        "WHERE e.last_status = 'pushed' AND a.status NOT IN ('booked', 'executed')")).scalars().all()
    if upsert_ids:
        db.execute(text("UPDATE appointment_google_events SET payload_hash = '' WHERE appointment_id = ANY(:ids)"),
                   {"ids": list(upsert_ids)})
    conn = db.connection()
    n_up = enqueue_appointments(conn, upsert_ids, step_seconds=RESYNC_STEP_SECONDS)
    n_del = enqueue_appointments(conn, delete_ids, step_seconds=RESYNC_STEP_SECONDS)
    return {"upserts": n_up, "deletes": n_del, "window_from": lo, "window_to": hi,
            "truncated": len(upsert_ids) >= RESYNC_MAX_APPOINTMENTS}
