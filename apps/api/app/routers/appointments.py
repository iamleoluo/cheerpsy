import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg2.extras import DateTimeTZRange
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.user import User
from app.schemas.appointment import (
    AppointmentBatchCreate,
    AppointmentCreate,
    AppointmentResponse,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def _make_number(therapist_code: str, dt: datetime, seq: int) -> str:
    date_str = dt.strftime("%Y%m%d")
    return f"R-{date_str}-{therapist_code}-{seq:03d}"


def _next_seq(db: Session, therapist_code: str, dt: datetime) -> int:
    date_str = dt.strftime("%Y%m%d")
    prefix = f"R-{date_str}-{therapist_code}-"
    result = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE appointment_number LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar()
    return (result or 0) + 1


def _next_visit_seq(db: Session, case_id: int) -> int:
    current_max = db.query(func.max(Appointment.visit_seq)).filter(
        Appointment.case_id == case_id
    ).scalar()
    return (current_max or 0) + 1


def _get_commission_rate(therapist: User) -> Decimal:
    if therapist.commission_rate is not None:
        return Decimal(str(therapist.commission_rate))
    return DEFAULT_COMMISSION_RATE


def _to_response(a: Appointment, therapist: User | None = None) -> AppointmentResponse:
    start = end = None
    if a.time_range:
        start = a.time_range.lower
        end = a.time_range.upper
    rate = _get_commission_rate(therapist) if therapist else DEFAULT_COMMISSION_RATE
    return AppointmentResponse(
        id=a.id,
        appointment_number=a.appointment_number,
        case_id=a.case_id,
        case_name=a.case.name if a.case else None,
        therapist_id=a.therapist_id,
        therapist_name=a.therapist.name if a.therapist else None,
        room_id=a.room_id,
        room_name=a.room.name if a.room else None,
        session_type=a.session_type,
        start_time=start,
        end_time=end,
        amount=float(a.amount),
        therapist_share=round(float(a.amount) * float(rate), 2),
        clinic_share=round(float(a.amount) * (1 - float(rate)), 2),
        visit_seq=a.visit_seq,
        status=a.status,
        batch_id=a.batch_id,
        created_at=a.created_at,
    )


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    start: datetime | None = None,
    end: datetime | None = None,
    status_filter: str | None = Query(None, alias="status"),
    case_id: int | None = None,
    room_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Appointment)
    if user.role == "therapist" and not room_id:
        query = query.filter(Appointment.therapist_id == user.id)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    if case_id:
        query = query.filter(Appointment.case_id == case_id)
    if room_id:
        query = query.filter(Appointment.room_id == room_id)
    if start and end:
        range_filter = f"[{start.isoformat()},{end.isoformat()})"
        query = query.filter(
            text("time_range && :r").bindparams(r=range_filter)
        )
    appointments = query.order_by(Appointment.id.desc()).limit(200).all()

    therapist_ids = list({a.therapist_id for a in appointments})
    therapists = {}
    if therapist_ids:
        users = db.query(User).filter(User.id.in_(therapist_ids)).all()
        therapists = {u.id: u for u in users}

    return [_to_response(a, therapists.get(a.therapist_id)) for a in appointments]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist)


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    therapist = user if user.role == "therapist" else db.query(User).filter(User.id == case.therapist_id).first()
    if not therapist or not therapist.therapist_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    if body.session_type == "in_person" and not body.room_id:
        raise HTTPException(status_code=400, detail="Room required for in-person sessions")

    if body.room_id:
        _check_room_conflict(db, body.room_id, body.start_time, body.end_time)

    seq = _next_seq(db, therapist.therapist_code, body.start_time)
    number = _make_number(therapist.therapist_code, body.start_time, seq)
    visit_seq = _next_visit_seq(db, body.case_id)

    time_range = DateTimeTZRange(body.start_time, body.end_time)
    appt = Appointment(
        appointment_number=number,
        case_id=body.case_id,
        therapist_id=therapist.id,
        room_id=body.room_id,
        session_type=body.session_type,
        time_range=time_range,
        amount=body.amount,
        visit_seq=visit_seq,
        status="booked",
        created_by=user.id,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return _to_response(appt, therapist)


@router.post("/batch", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
def create_batch(
    body: AppointmentBatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    therapist = user if user.role == "therapist" else db.query(User).filter(User.id == case.therapist_id).first()
    if not therapist or not therapist.therapist_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    batch_id = str(uuid.uuid4())[:8]
    next_vs = _next_visit_seq(db, body.case_id)
    results = []

    for i, slot in enumerate(body.slots):
        amount = slot.amount if slot.amount is not None else body.amount

        if body.room_id:
            _check_room_conflict(db, body.room_id, slot.start_time, slot.end_time)

        seq = _next_seq(db, therapist.therapist_code, slot.start_time)
        number = _make_number(therapist.therapist_code, slot.start_time, seq)
        time_range = DateTimeTZRange(slot.start_time, slot.end_time)

        appt = Appointment(
            appointment_number=number,
            case_id=body.case_id,
            therapist_id=therapist.id,
            room_id=body.room_id,
            session_type=body.session_type,
            time_range=time_range,
            amount=amount,
            visit_seq=next_vs + i,
            status="booked",
            batch_id=batch_id,
            created_by=user.id,
        )
        db.add(appt)
        db.flush()
        results.append(appt)

    db.commit()
    for a in results:
        db.refresh(a)
    return [_to_response(a, therapist) for a in results]


@router.put("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"Cannot cancel appointment with status '{a.status}'")

    today = date.today()
    appt_date = a.time_range.lower.date() if a.time_range else None
    if appt_date and appt_date < today:
        raise HTTPException(status_code=400, detail="Cannot cancel past appointments")

    a.status = "cancelled"
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist)


def _check_room_conflict(db: Session, room_id: int, start: datetime, end: datetime):
    conflict = db.execute(
        text("""
            SELECT id FROM appointments
            WHERE room_id = :room_id
              AND status != 'cancelled'
              AND time_range && tstzrange(:start, :end)
            LIMIT 1
        """),
        {"room_id": room_id, "start": start.isoformat(), "end": end.isoformat()},
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="Room time slot conflict")
