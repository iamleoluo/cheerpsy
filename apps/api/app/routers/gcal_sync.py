"""Google 日曆同步的工作佇列狀態與補救（docs/gcal-sync-plan.md §2.3-7、§6）。

admin 與 staff 可看狀態、按「重試失敗工作」；「全部重新同步」只有 admin。
回應只含預約編號、心理師名稱、時間與錯誤摘要，不含個案資料或任何 token。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.gcal import GoogleOAuthConnection
from app.models.user import User
from app.services import gcal_sync
from app.services.audit import write_audit

router = APIRouter(prefix="/settings/google/sync", tags=["settings"])

ADMIN = RequireRole(["admin"])
ADMIN_OR_STAFF = RequireRole(["admin", "staff"])


class ProblemJob(BaseModel):
    id: int
    status: str  # failed / blocked
    attempts: int
    last_error: str | None = None
    appointment_id: int
    appointment_number: str
    therapist_name: str
    starts_at: datetime | None = None
    updated_at: datetime | None = None


class SyncStatus(BaseModel):
    counts: dict[str, int]
    problems: list[ProblemJob]
    oldest_due_seconds: int | None = None  # 最久一筆「已到期卻還沒處理」多久了；很大代表工作者可能沒在跑
    connection_status: str
    can_resync: bool


class ActionResult(BaseModel):
    status: SyncStatus
    message: str


def _require_active(db: Session) -> GoogleOAuthConnection:
    conn = db.get(GoogleOAuthConnection, 1)
    if conn is None or conn.status != "active":
        raise HTTPException(status_code=409, detail="Google 尚未連結或授權已失效，請管理員先到「系統管理 → 日曆同步」連結")
    return conn


def _status(db: Session, user: User) -> SyncStatus:
    conn = db.get(GoogleOAuthConnection, 1)
    due = db.execute(text(
        "SELECT extract(epoch FROM now() - min(next_attempt_at)) FROM gcal_outbox "
        "WHERE status IN ('pending', 'retry') AND next_attempt_at <= now()")).scalar()
    return SyncStatus(
        counts=gcal_sync.counts(db),
        problems=[ProblemJob(**r) for r in gcal_sync.problem_jobs(db)],
        oldest_due_seconds=int(due) if due is not None else None,
        connection_status=conn.status if conn else "disconnected",
        can_resync=user.role == "admin",
    )


@router.get("", response_model=SyncStatus)
def get_sync_status(user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    return _status(db, user)


@router.post("/retry", response_model=ActionResult)
def retry_failed(user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    """把「失敗」與「被擋住」的工作全部重新排入（次數歸零）。"""
    _require_active(db)
    n = gcal_sync.requeue(db)
    write_audit(db, "gcal_outbox", 0, "RETRY", user.id, None, {"requeued": n})
    db.commit()
    return ActionResult(status=_status(db, user), message=f"已重新排入 {n} 筆工作")


@router.post("/resync", response_model=ActionResult)
def resync_all(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """全部重新同步：把同步區間內所有預約重新推到 Google（用於首次上線匯入與補救）。分散排程，不會瞬間打爆。"""
    _require_active(db)
    r = gcal_sync.resync_all(db)
    write_audit(db, "gcal_outbox", 0, "RESYNC", user.id, None,
                {"upserts": r["upserts"], "deletes": r["deletes"],
                 "from": r["window_from"].isoformat(), "to": r["window_to"].isoformat()})
    db.commit()
    msg = f"已排入 {r['upserts']} 筆新增／更新、{r['deletes']} 筆刪除，會在背景陸續推送"
    if r["truncated"]:
        msg += f"（超過 {gcal_sync.RESYNC_MAX_APPOINTMENTS} 筆，請縮小同步區間後再按一次）"
    return ActionResult(status=_status(db, user), message=msg)
