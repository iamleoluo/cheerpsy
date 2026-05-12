from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.user import User

router = APIRouter(prefix="/churn", tags=["churn"])


@router.get("")
def churn_warning_list(
    inactive_days: int = Query(default=30, ge=7, le=180),
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = now - timedelta(days=inactive_days)

    active_cases = db.query(Case).filter(Case.status.in_(["initial", "ongoing"])).all()

    result = []
    for case in active_cases:
        last_appt = (
            db.query(Appointment)
            .filter(
                Appointment.case_id == case.id,
                Appointment.status.in_(["booked", "executed"]),
            )
            .order_by(text("upper(time_range) DESC"))
            .first()
        )

        has_future = False
        if last_appt and last_appt.time_range:
            range_str = str(last_appt.time_range)
            end_part = range_str.split(",")[1].rstrip(")").strip() if "," in range_str else None
            if end_part:
                try:
                    end_dt = datetime.fromisoformat(end_part.replace('"', ''))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    if end_dt > now:
                        has_future = True
                    elif end_dt < cutoff:
                        therapist = db.query(User).filter(User.id == case.therapist_id).first()
                        days_since = (now - end_dt).days
                        result.append({
                            "case_id": case.id,
                            "case_name": case.name,
                            "therapist_name": therapist.name if therapist else None,
                            "phone": case.phone,
                            "status": case.status,
                            "last_appointment_date": end_dt.date().isoformat(),
                            "days_since_last": days_since,
                            "funding_source": case.funding_source,
                        })
                        continue
                except (ValueError, IndexError):
                    pass

        if not last_appt and not has_future:
            therapist = db.query(User).filter(User.id == case.therapist_id).first()
            result.append({
                "case_id": case.id,
                "case_name": case.name,
                "therapist_name": therapist.name if therapist else None,
                "phone": case.phone,
                "status": case.status,
                "last_appointment_date": None,
                "days_since_last": None,
                "funding_source": case.funding_source,
            })

    result.sort(key=lambda x: x["days_since_last"] or 9999, reverse=True)
    return result
