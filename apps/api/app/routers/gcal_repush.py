"""單一心理師重新推送（docs/gcal-sync-plan.md PR E）：行政、管理員限定。

把該心理師「未來」的 booked 預約重新排進 outbox（並清掉雜湊，強制覆寫 Google 上被改過的內容）。
冪等：已經在排隊（pending／running／retry）的不重複加入；重複呼叫第二次 queued 為 0。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.gcal_hooks import enqueue_appointments
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/gcal", tags=["gcal"])

ADMIN_OR_STAFF = RequireRole(["admin", "staff"])


class RepushOut(BaseModel):
    queued: int  # 這次新排入的筆數
    already_queued: int  # 本來就在排隊、未重複加入的筆數
    message: str


@router.post("/therapists/{therapist_id}/repush", response_model=RepushOut)
def repush_therapist(
    therapist_id: int,
    user: User = Depends(ADMIN_OR_STAFF),
    db: Session = Depends(get_db),
):
    t = db.query(User).filter(User.id == therapist_id, User.role == "therapist").first()
    if t is None:
        raise HTTPException(status_code=404, detail="找不到這位心理師")
    now = datetime.now(timezone.utc)
    ids = db.execute(text(
        "SELECT id FROM appointments WHERE therapist_id = :t AND status = 'booked' AND lower(time_range) >= :now "
        "ORDER BY id"), {"t": therapist_id, "now": now}).scalars().all()
    waiting = set(db.execute(text(
        "SELECT appointment_id FROM gcal_outbox WHERE appointment_id = ANY(:ids) "
        "AND status IN ('pending', 'running', 'retry')"), {"ids": list(ids)}).scalars().all()) if ids else set()
    todo = [i for i in ids if i not in waiting]
    if todo:
        db.execute(text("UPDATE appointment_google_events SET payload_hash = '' WHERE appointment_id = ANY(:ids)"),
                   {"ids": todo})
    queued = enqueue_appointments(db.connection(), todo, step_seconds=0.3)
    write_audit(db, "gcal_outbox", therapist_id, "REPUSH", user.id, None,
                {"therapist_id": therapist_id, "queued": queued, "already_queued": len(waiting)})
    db.commit()
    return RepushOut(queued=queued, already_queued=len(waiting),
                     message=f"已排入 {queued} 筆未來預約，另有 {len(waiting)} 筆本來就在排隊")
