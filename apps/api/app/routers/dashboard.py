from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.petty_cash import PettyCash
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    year, month = today.year, today.month

    base_q = db.query(SessionRecord).filter(
        extract("year", SessionRecord.session_date) == year,
        extract("month", SessionRecord.session_date) == month,
        SessionRecord.is_void.is_(False),
    )
    if user.role == "therapist":
        base_q = base_q.filter(SessionRecord.therapist_id == user.id)

    records = base_q.all()
    session_count = len(records)

    def _eff(r):
        return float(r.amount) - float(r.discount_amount or 0)

    total_revenue = sum(_eff(r) for r in records)
    unpaid_count = sum(1 for r in records if r.payment_status in ("unpaid", "claiming"))
    unpaid_amount = sum(_eff(r) for r in records if r.payment_status in ("unpaid", "claiming"))

    # Upcoming 7-day appointments needing reminders
    day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=7)
    range_str = f"[{day_start.isoformat()},{day_end.isoformat()})"

    reminder_q = db.query(func.count(Appointment.id)).filter(
        Appointment.status == "booked",
        text("time_range && :r").bindparams(r=range_str),
    )
    if user.role == "therapist":
        reminder_q = reminder_q.filter(Appointment.therapist_id == user.id)
    upcoming_count = reminder_q.scalar() or 0

    # Active case count
    case_q = db.query(func.count(Case.id)).filter(Case.status.in_(["initial", "ongoing"]))
    if user.role == "therapist":
        case_q = case_q.filter(Case.therapist_id == user.id)
    active_cases = case_q.scalar() or 0

    # Petty cash balance (admin/accountant only)
    petty_balance = None
    petty_alert = False
    if user.role in ("admin", "accountant"):
        last_petty = db.query(PettyCash).order_by(PettyCash.id.desc()).first()
        if last_petty:
            petty_balance = float(last_petty.balance_after)
            petty_alert = petty_balance < 3000

    # Churn warning count (cases with no future appointments, status ongoing)
    churn_count = 0
    if user.role in ("admin", "accountant"):
        now_str = f"[{day_start.isoformat()},)"
        active_case_ids = [c.id for c in db.query(Case.id).filter(Case.status.in_(["initial", "ongoing"])).all()]
        if active_case_ids:
            cases_with_future = set(
                r[0] for r in db.query(Appointment.case_id).filter(
                    Appointment.case_id.in_(active_case_ids),
                    Appointment.status == "booked",
                    text("time_range && :r").bindparams(r=now_str),
                ).distinct().all()
            )
            churn_count = len(set(active_case_ids) - cases_with_future)

    return {
        "session_count": session_count,
        "total_revenue": total_revenue,
        "unpaid_count": unpaid_count,
        "unpaid_amount": unpaid_amount,
        "upcoming_reminders": upcoming_count,
        "active_cases": active_cases,
        "petty_balance": petty_balance,
        "petty_alert": petty_alert,
        "churn_count": churn_count,
    }
