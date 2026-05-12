from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
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

    paid_count = sum(1 for r in records if r.payment_status in ("paid", "claimed"))
    unpaid_count = sum(1 for r in records if r.payment_status in ("unpaid", "claiming"))

    # Session type breakdown
    by_type: dict[str, dict] = {}
    for r in records:
        t = r.session_type or "unknown"
        if t not in by_type:
            by_type[t] = {"count": 0, "revenue": 0.0}
        by_type[t]["count"] += 1
        by_type[t]["revenue"] += float(r.amount)

    # Funding source breakdown (self_pay vs institution advance)
    self_pay_revenue = 0.0
    institution_revenue = 0.0
    institution_unpaid = 0.0
    for r in records:
        case = None
        if r.appointment:
            case = r.appointment.case
        elif r.case_id:
            case = db.query(Case).filter(Case.id == r.case_id).first()

        funding = case.funding_source if case else "self_pay"
        if funding == "institution":
            institution_revenue += float(r.amount)
            if r.payment_status in ("unpaid", "claiming"):
                institution_unpaid += float(r.amount)
        else:
            self_pay_revenue += float(r.amount)

    # Therapist summary
    by_therapist: dict[int, dict] = {}
    for r in records:
        tid = r.therapist_id
        if tid not in by_therapist:
            by_therapist[tid] = {"therapist_id": tid, "sessions": 0, "revenue": 0.0, "share": 0.0}
        by_therapist[tid]["sessions"] += 1
        by_therapist[tid]["revenue"] += float(r.amount)
        by_therapist[tid]["share"] += round(float(r.amount) * 0.7, 2)

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

    # Petty cash
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

    # Appointment stats
    month_appts = (
        db.query(Appointment)
        .filter(
            extract("year", Appointment.created_at) == year,
            extract("month", Appointment.created_at) == month,
        )
        .all()
    )
    booked = sum(1 for a in month_appts if a.status == "booked")
    cancelled = sum(1 for a in month_appts if a.status == "cancelled")
    cancelled_amount = sum(float(a.amount) for a in month_appts if a.status == "cancelled")

    # KPIs
    total_appts = booked + session_count + cancelled
    cancel_rate = round(cancelled / total_appts * 100, 1) if total_appts > 0 else 0

    # Continuation rate: cases with >1 session this month
    case_session_counts: dict[int, int] = {}
    for r in records:
        if r.case_id:
            case_session_counts[r.case_id] = case_session_counts.get(r.case_id, 0) + 1
    cases_with_sessions = len(case_session_counts)
    continuing_cases = sum(1 for c in case_session_counts.values() if c > 1)
    continuation_rate = round(continuing_cases / cases_with_sessions * 100, 1) if cases_with_sessions > 0 else 0

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
        "session_type_breakdown": by_type,
        "funding_breakdown": {
            "self_pay_revenue": self_pay_revenue,
            "institution_revenue": institution_revenue,
            "institution_unpaid": institution_unpaid,
        },
        "pnl": {
            "gross_revenue": total_revenue,
            "therapist_cost": total_therapist,
            "clinic_gross": total_clinic,
            "petty_cash_expense": petty_total,
            "net_income": total_clinic + petty_total,
            "cancelled_loss": cancelled_amount,
        },
        "kpi": {
            "cancel_rate": cancel_rate,
            "continuation_rate": continuation_rate,
            "active_therapists": len(by_therapist),
            "unique_cases": cases_with_sessions,
        },
        "therapist_summary": therapist_summary,
        "petty_cash_by_category": by_category,
        "appointment_stats": {
            "booked": booked,
            "cancelled": cancelled,
            "executed": session_count,
        },
    }


@router.get("/reconciliation")
def reconciliation_report(
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
        .order_by(SessionRecord.session_date)
        .all()
    )

    self_pay_records = []
    institution_groups: dict[str, list] = {}

    for r in records:
        case = None
        if r.appointment:
            case = r.appointment.case
        elif r.case_id:
            case = db.query(Case).filter(Case.id == r.case_id).first()

        funding = case.funding_source if case else "self_pay"
        institution_name = None
        if case and case.institution:
            institution_name = case.institution.name

        therapist = None
        if r.appointment:
            therapist = r.appointment.therapist
        else:
            therapist = db.query(User).filter(User.id == r.therapist_id).first()

        row = {
            "id": r.id,
            "session_date": r.session_date.isoformat(),
            "case_id": r.case_id,
            "case_name": case.name if case else None,
            "therapist_name": therapist.name if therapist else None,
            "amount": float(r.amount),
            "payment_status": r.payment_status,
            "claim_number": r.claim_number,
            "receipt_number": r.receipt_number,
        }

        if funding == "institution":
            key = institution_name or "未知機構"
            institution_groups.setdefault(key, []).append(row)
        else:
            self_pay_records.append(row)

    # Summaries
    def summarize(recs):
        total = sum(r["amount"] for r in recs)
        paid = sum(r["amount"] for r in recs if r["payment_status"] in ("paid", "claimed"))
        unpaid = sum(r["amount"] for r in recs if r["payment_status"] in ("unpaid", "claiming"))
        return {"total": total, "paid": paid, "unpaid": unpaid, "count": len(recs)}

    institution_summaries = []
    for name, recs in sorted(institution_groups.items()):
        institution_summaries.append({
            "institution_name": name,
            "summary": summarize(recs),
            "records": recs,
        })

    return {
        "year": year,
        "month": month,
        "self_pay": {
            "summary": summarize(self_pay_records),
            "records": self_pay_records,
        },
        "institutions": institution_summaries,
    }
