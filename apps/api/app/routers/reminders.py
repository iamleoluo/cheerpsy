from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.reminder_log import ReminderLog
from app.models.user import User

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    appointment_id: int
    contact_result: str  # confirmed, wants_cancel, no_answer
    notes: str | None = None


class ReminderResponse(BaseModel):
    id: int
    appointment_id: int
    contact_result: str
    notes: str | None
    contacted_by: int | None
    contacted_at: str | None
    model_config = {"from_attributes": True}


@router.get("/upcoming")
def upcoming_appointments(
    days: int = Query(default=3, ge=1, le=14),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(days=days)
    range_str = f"[{today.isoformat()},{end.isoformat()})"

    q = (
        db.query(Appointment)
        .filter(
            Appointment.status == "booked",
            text("time_range && :r").bindparams(r=range_str),
        )
        .order_by(text("lower(time_range)"))
    )
    if user.role == "therapist":
        q = q.filter(Appointment.therapist_id == user.id)

    appointments = q.all()

    result = []
    for a in appointments:
        case = a.case
        therapist = a.therapist
        logs = db.query(ReminderLog).filter(ReminderLog.appointment_id == a.id).order_by(ReminderLog.contacted_at.desc()).all()
        result.append({
            "appointment_id": a.id,
            "appointment_number": a.appointment_number,
            "case_id": a.case_id,
            "case_name": case.name if case else None,
            "case_phone": case.phone if case else None,
            "therapist_name": therapist.name if therapist else None,
            "session_type": a.session_type,
            "start_time": str(a.time_range).split(",")[0].lstrip("[") if a.time_range else None,
            "status": a.status,
            "reminder_count": len(logs),
            "last_contact_result": logs[0].contact_result if logs else None,
        })

    return result


@router.get("/logs/{appointment_id}")
def get_reminder_logs(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(ReminderLog)
        .filter(ReminderLog.appointment_id == appointment_id)
        .order_by(ReminderLog.contacted_at.desc())
        .all()
    )
    result = []
    for log in logs:
        contacted_by_name = None
        if log.contacted_by:
            u = db.query(User).filter(User.id == log.contacted_by).first()
            contacted_by_name = u.name if u else None
        result.append({
            "id": log.id,
            "contact_result": log.contact_result,
            "notes": log.notes,
            "contacted_by": log.contacted_by,
            "contacted_by_name": contacted_by_name,
            "contacted_at": log.contacted_at.isoformat() if log.contacted_at else None,
        })
    return result


@router.post("", status_code=201)
def create_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(Appointment.id == body.appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    log = ReminderLog(
        appointment_id=body.appointment_id,
        contact_result=body.contact_result,
        notes=body.notes,
        contacted_by=user.id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "status": "created"}
