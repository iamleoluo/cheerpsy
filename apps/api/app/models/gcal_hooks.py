"""預約寫入時，在「同一個交易」裡把 Google 同步工作寫進 outbox（docs/gcal-sync-plan.md §2.1、§2.3）。

用 SQLAlchemy 的 flush 事件，而不是在每個路由手動呼叫：新增、批次、改期、換診間、改心理師、取消、
未到、報到執行（含結算流程）都會經過 ORM，一處掛鉤就全部涵蓋，也不必改動結算相關檔案。
入列用同一條資料庫連線的 SQL，所以預約被 rollback 時工作也一併消失；入列失敗也不會讓預約寫入失敗
以外的事發生——它只是一句 INSERT，沒有任何對外呼叫。

不經過 ORM 的批次 UPDATE（目前只有結案時取消未來預約）要明確呼叫 `enqueue_appointments`。
"""

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session

from app.models.appointment import Appointment

# 這些欄位改變，Google 上的事件就需要跟著變（或刪除）。金額、備註、報到時間等不影響事件內容，不入列
WATCHED = ("time_range", "room_id", "status", "therapist_id", "session_type", "case_id",
           "couple_case_id", "is_intake")

_ENQUEUE_SQL = text("""
INSERT INTO gcal_outbox (job_type, appointment_id, dedupe_key, status, attempts, next_attempt_at, version,
                         created_at, updated_at)
SELECT CASE WHEN a.status IN ('booked', 'executed') THEN 'upsert_event' ELSE 'delete_event' END,
       a.id, 'appt:' || a.id, :status, 0,
       now() + (row_number() OVER (ORDER BY a.id) - 1) * :step * interval '1 second', 1, now(), now()
FROM appointments a WHERE a.id = ANY(:ids)
ON CONFLICT (dedupe_key) DO UPDATE SET
    job_type = EXCLUDED.job_type, status = EXCLUDED.status, attempts = 0, next_attempt_at = EXCLUDED.next_attempt_at,
    last_error = NULL, claimed_at = NULL, finished_at = NULL, updated_at = now(),
    version = gcal_outbox.version + 1
""")


def enqueue_appointments(connection, ids, step_seconds: float = 0) -> int:
    """把這些預約排入同步（每個預約一列；已有就重設為待處理）。回傳入列數。
    step_seconds：大量入列時，每筆之間錯開幾秒（「全部重新同步」用，避免一次打爆單一日曆）。

    - 沒有 Google 連線（從未連結或已解除）：不入列。上線時用「全部重新同步」補齊既有預約。
    - 連線授權失效：入列為 blocked，重新連結後按「重試」即可。
    只是同交易內的 SQL，不會對外連線、不會拋出與預約無關的錯誤。"""
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return 0
    conn_status = connection.execute(text("SELECT status FROM google_oauth_connections WHERE id = 1")).scalar()
    if conn_status is None or conn_status == "disconnected":
        return 0
    status = "blocked" if conn_status == "token_invalid" else "pending"
    connection.execute(_ENQUEUE_SQL, {"status": status, "ids": ids, "step": step_seconds})
    return len(ids)


_ENQUEUE_DELETED_SQL = text("""
INSERT INTO gcal_outbox (job_type, appointment_id, dedupe_key, status, attempts, next_attempt_at, version,
                         created_at, updated_at)
SELECT 'delete_event', i, 'appt:' || i, :status, 0, now(), 1, now(), now()
FROM unnest(CAST(:ids AS integer[])) AS i
WHERE EXISTS (SELECT 1 FROM appointment_google_events e WHERE e.appointment_id = i AND e.last_status = 'pushed')
ON CONFLICT (dedupe_key) DO UPDATE SET
    job_type = 'delete_event', status = EXCLUDED.status, attempts = 0, next_attempt_at = now(),
    last_error = NULL, claimed_at = NULL, finished_at = NULL, updated_at = now(),
    version = gcal_outbox.version + 1
""")


def enqueue_deleted(connection, ids) -> int:
    """預約被刪除：Google 上若已有對應事件，排入刪除（預約列已不存在，所以不從 appointments 取資料）。"""
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return 0
    conn_status = connection.execute(text("SELECT status FROM google_oauth_connections WHERE id = 1")).scalar()
    if conn_status is None or conn_status == "disconnected":
        return 0
    connection.execute(_ENQUEUE_DELETED_SQL, {"status": "blocked" if conn_status == "token_invalid" else "pending", "ids": ids})
    return len(ids)


_KEY = "gcal_outbox_pending"


@event.listens_for(Session, "before_flush")
def _collect(session: Session, flush_context, instances) -> None:
    box = session.info.setdefault(_KEY, {"new": [], "ids": set(), "deleted": set()})
    for obj in session.new:
        if isinstance(obj, Appointment):
            box["new"].append(obj)
    for obj in session.deleted:
        if isinstance(obj, Appointment) and obj.id is not None:
            box["deleted"].add(obj.id)
    for obj in session.dirty:
        if isinstance(obj, Appointment) and obj.id is not None:
            state = inspect(obj)
            if any(state.attrs[name].history.has_changes() for name in WATCHED):
                box["ids"].add(obj.id)


@event.listens_for(Session, "after_flush")
def _enqueue(session: Session, flush_context) -> None:
    box = session.info.pop(_KEY, None)
    if not box:
        return
    ids = set(box["ids"]) | {o.id for o in box["new"] if o.id is not None}
    if ids:
        enqueue_appointments(session.connection(), ids)
    if box["deleted"]:
        enqueue_deleted(session.connection(), box["deleted"])
