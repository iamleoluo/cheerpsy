from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.session_record import SessionRecord
from app.models.therapist_payout import PayoutDetail, TherapistPayout
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/payouts", tags=["payouts"])

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def _get_rate(sr: SessionRecord) -> Decimal:
    if sr.commission_rate_used is not None:
        return Decimal(str(sr.commission_rate_used))
    return DEFAULT_COMMISSION_RATE


class PayoutResponse(BaseModel):
    id: int
    therapist_id: int
    therapist_name: str | None = None
    payout_month: str
    total_amount: float
    session_count: int = 0
    status: str
    paid_at: str | None = None


@router.get("", response_model=list[PayoutResponse])
def list_payouts(
    payout_month: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TherapistPayout)
    if user.role == "therapist":
        q = q.filter(TherapistPayout.therapist_id == user.id)
    if payout_month:
        q = q.filter(TherapistPayout.payout_month == payout_month)
    payouts = q.order_by(TherapistPayout.payout_month.desc(), TherapistPayout.id).all()

    therapist_ids = list({p.therapist_id for p in payouts})
    names = {}
    if therapist_ids:
        users = db.query(User).filter(User.id.in_(therapist_ids)).all()
        names = {u.id: u.name for u in users}

    result = []
    for p in payouts:
        detail_count = db.query(PayoutDetail).filter(PayoutDetail.payout_id == p.id).count()
        result.append(PayoutResponse(
            id=p.id,
            therapist_id=p.therapist_id,
            therapist_name=names.get(p.therapist_id),
            payout_month=p.payout_month,
            total_amount=float(p.total_amount),
            session_count=detail_count,
            status=p.status,
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
        ))
    return result


@router.get("/{payout_id}/details")
def payout_details(
    payout_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payout = db.query(TherapistPayout).filter(TherapistPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if user.role == "therapist" and payout.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    details = db.query(PayoutDetail).filter(PayoutDetail.payout_id == payout_id).all()
    sessions = []
    for d in details:
        sr = db.query(SessionRecord).filter(SessionRecord.id == d.session_id).first()
        if sr:
            rate = _get_rate(sr)
            sessions.append({
                "session_id": sr.id,
                "session_date": sr.session_date.isoformat(),
                "amount": float(sr.amount),
                "therapist_share": round(float(sr.amount) * float(rate), 2),
                "fee_category": sr.fee_category,
                "session_type": sr.session_type,
            })
    return {"payout_id": payout_id, "sessions": sessions}


class GeneratePayoutRequest(BaseModel):
    payout_month: str  # YYYY-MM


@router.post("/generate")
def generate_payouts(
    body: GeneratePayoutRequest,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    parts = body.payout_month.split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    year, month = int(parts[0]), int(parts[1])

    existing = db.query(TherapistPayout).filter(TherapistPayout.payout_month == body.payout_month).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{body.payout_month} 酬勞已產生，請勿重複產生")

    records = (
        db.query(SessionRecord)
        .filter(
            extract("year", SessionRecord.session_date) == year,
            extract("month", SessionRecord.session_date) == month,
        )
        .all()
    )

    by_therapist: dict[int, list[SessionRecord]] = {}
    for r in records:
        by_therapist.setdefault(r.therapist_id, []).append(r)

    created = 0
    for tid, recs in by_therapist.items():
        total = sum(round(float(r.amount) * float(_get_rate(r)), 2) for r in recs)
        payout = TherapistPayout(
            therapist_id=tid,
            payout_month=body.payout_month,
            total_amount=total,
            status="pending",
            created_by=user.id,
        )
        db.add(payout)
        db.flush()

        for r in recs:
            db.add(PayoutDetail(payout_id=payout.id, session_id=r.id))
        created += 1

    db.commit()
    return {"month": body.payout_month, "payouts_created": created}


@router.put("/{payout_id}/pay")
def mark_paid(
    payout_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    payout = db.query(TherapistPayout).filter(TherapistPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status == "paid":
        raise HTTPException(status_code=400, detail="Already paid")
    payout.status = "paid"
    payout.paid_at = datetime.now(timezone.utc)
    write_audit(db, "therapist_payouts", payout.id, "UPDATE", user.id,
                {"status": "pending"}, {"status": "paid", "paid_at": payout.paid_at.isoformat()})
    db.commit()
    return {"status": "paid"}
