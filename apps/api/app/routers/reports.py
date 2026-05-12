from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.appointment import Appointment
from app.models.petty_cash import PettyCash
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
def monthly_report(
    year: int = Query(...),
    month: int = Query(...),
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    records = (
        db.query(SessionRecord)
        .filter(
            extract("year", SessionRecord.session_date) == year,
            extract("month", SessionRecord.session_date) == month,
        )
        .all()
    )

    total_revenue = sum(float(r.amount) for r in records)
    total_therapist = sum(round(float(r.amount) * 0.7, 2) for r in records)
    total_clinic = sum(round(float(r.amount) * 0.3, 2) for r in records)
    session_count = len(records)

    paid_count = sum(1 for r in records if r.payment_status in ("paid", "reconciled"))
    unpaid_count = sum(1 for r in records if r.payment_status in ("unpaid", "pending_claim", "claiming"))

    by_therapist: dict[str, dict] = {}
    for r in records:
        name = r.therapist_id
        if name not in by_therapist:
            by_therapist[name] = {"therapist_id": r.therapist_id, "sessions": 0, "revenue": 0.0, "share": 0.0}
        by_therapist[name]["sessions"] += 1
        by_therapist[name]["revenue"] += float(r.amount)
        by_therapist[name]["share"] += round(float(r.amount) * 0.7, 2)

    therapist_names = {}
    if by_therapist:
        users = db.query(User).filter(User.id.in_(by_therapist.keys())).all()
        therapist_names = {u.id: u.name for u in users}

    therapist_summary = []
    for tid, data in by_therapist.items():
        therapist_summary.append({
            "therapist_id": tid,
            "therapist_name": therapist_names.get(tid, ""),
            "sessions": data["sessions"],
            "revenue": data["revenue"],
            "therapist_share": data["share"],
            "clinic_share": round(data["revenue"] - data["share"], 2),
        })
    therapist_summary.sort(key=lambda x: x["revenue"], reverse=True)

    petty = (
        db.query(PettyCash)
        .filter(
            extract("year", PettyCash.date) == year,
            extract("month", PettyCash.date) == month,
        )
        .all()
    )
    petty_total = sum(float(p.amount) for p in petty)

    by_category: dict[str, float] = {}
    for p in petty:
        by_category[p.category] = by_category.get(p.category, 0) + float(p.amount)

    booked = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.status == "booked",
            extract("year", Appointment.created_at) == year,
            extract("month", Appointment.created_at) == month,
        )
        .scalar()
        or 0
    )
    cancelled = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.status == "cancelled",
            extract("year", Appointment.created_at) == year,
            extract("month", Appointment.created_at) == month,
        )
        .scalar()
        or 0
    )

    return {
        "year": year,
        "month": month,
        "summary": {
            "total_revenue": total_revenue,
            "total_therapist_share": total_therapist,
            "total_clinic_share": total_clinic,
            "session_count": session_count,
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
            "petty_cash_total": petty_total,
            "net_clinic_income": total_clinic + petty_total,
        },
        "therapist_summary": therapist_summary,
        "petty_cash_by_category": by_category,
        "appointment_stats": {
            "booked": booked,
            "cancelled": cancelled,
            "executed": session_count,
        },
    }
