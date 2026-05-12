from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.session_record import SessionRecord
from app.models.user import User
from app.schemas.session_record import (
    SessionRecordResponse,
    SessionRecordUpdatePayment,
    SettlementRequest,
    SettlementResponse,
)
from app.services.settlement import run_daily_settlement


def _write_audit(db: Session, table: str, record_id: int, op: str, user_id: int, before: dict | None, after: dict | None, reason: str | None = None):
    db.add(AuditLog(
        table_name=table,
        record_id=record_id,
        operation=op,
        changed_by=user_id,
        before_data=before,
        after_data=after,
        reason=reason,
    ))

router = APIRouter(prefix="/ledger", tags=["ledger"])


def _to_response(r: SessionRecord, db: Session) -> SessionRecordResponse:
    appt = r.appointment
    case = appt.case if appt else (db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None)
    therapist = appt.therapist if appt else db.query(User).filter(User.id == r.therapist_id).first()
    return SessionRecordResponse(
        id=r.id,
        appointment_id=r.appointment_id,
        appointment_number=appt.appointment_number if appt else None,
        session_date=r.session_date,
        case_id=r.case_id,
        case_name=case.name if case else None,
        therapist_id=r.therapist_id,
        therapist_name=therapist.name if therapist else None,
        session_type=r.session_type,
        room_id=r.room_id,
        fee_category=r.fee_category,
        amount=float(r.amount),
        therapist_share=round(float(r.amount) * 0.7, 2),
        clinic_share=round(float(r.amount) * 0.3, 2),
        payment_status=r.payment_status,
        funding_source=case.funding_source if case else None,
        institution_name=case.institution.name if case and case.institution else None,
        payment_method=r.payment_method,
        payment_note=r.payment_note,
        claim_number=r.claim_number,
        receipt_number=r.receipt_number,
        locked_at=r.locked_at,
    )


@router.get("", response_model=list[SessionRecordResponse])
def list_records(
    payment_status: str | None = Query(None, alias="payment_status"),
    therapist_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(SessionRecord)
    if user.role == "therapist":
        query = query.filter(SessionRecord.therapist_id == user.id)
    elif therapist_id:
        query = query.filter(SessionRecord.therapist_id == therapist_id)
    if payment_status:
        query = query.filter(SessionRecord.payment_status == payment_status)
    records = query.order_by(SessionRecord.session_date.desc()).limit(200).all()
    return [_to_response(r, db) for r in records]


@router.get("/{record_id}", response_model=SessionRecordResponse)
def get_record(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if user.role == "therapist" and r.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return _to_response(r, db)


@router.put("/{record_id}/payment", response_model=SessionRecordResponse)
def update_payment_status(
    record_id: int,
    body: SessionRecordUpdatePayment,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.locked_at:
        raise HTTPException(status_code=400, detail="Record is locked")

    case = r.appointment.case if r.appointment else (
        db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None
    )
    funding = case.funding_source if case else "self_pay"

    SELF_PAY_TRANSITIONS = {"unpaid": ["paid"]}
    INSTITUTION_TRANSITIONS = {"unpaid": ["claiming"], "claiming": ["claimed"]}

    transitions = SELF_PAY_TRANSITIONS if funding == "self_pay" else INSTITUTION_TRANSITIONS
    allowed = transitions.get(r.payment_status, [])
    if body.payment_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change from '{r.payment_status}' to '{body.payment_status}'",
        )

    if body.payment_status == "paid":
        if not body.payment_method or body.payment_method not in ("cash", "transfer"):
            raise HTTPException(status_code=400, detail="請選擇收款方式（現金或匯款）")
        r.payment_method = body.payment_method
        if body.payment_method == "transfer":
            if not body.payment_note or not body.payment_note.strip():
                raise HTTPException(status_code=400, detail="匯款資訊為必填（如帳戶末五碼）")
            r.payment_note = body.payment_note.strip()
        else:
            r.payment_note = body.payment_note.strip() if body.payment_note else None

    if body.payment_status == "claiming":
        if not body.claim_number or not body.claim_number.strip():
            raise HTTPException(status_code=400, detail="請款單號為必填")
        r.claim_number = body.claim_number.strip()

    if body.payment_status == "claimed":
        if not body.receipt_number or not body.receipt_number.strip():
            raise HTTPException(status_code=400, detail="到款收據/單號為必填")
        r.receipt_number = body.receipt_number.strip()

    before = {"payment_status": r.payment_status, "payment_method": r.payment_method, "claim_number": r.claim_number, "receipt_number": r.receipt_number}
    r.payment_status = body.payment_status
    after = {"payment_status": r.payment_status, "payment_method": r.payment_method, "claim_number": r.claim_number, "receipt_number": r.receipt_number}
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/lock", response_model=SessionRecordResponse)
def lock_record(
    record_id: int,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.locked_at:
        raise HTTPException(status_code=400, detail="Already locked")
    r.locked_at = datetime.now(timezone.utc)
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, {"locked_at": None}, {"locked_at": r.locked_at.isoformat()})
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


class UnlockRequest(BaseModel):
    reason: str


@router.put("/{record_id}/unlock", response_model=SessionRecordResponse)
def unlock_record(
    record_id: int,
    body: UnlockRequest,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if not r.locked_at:
        raise HTTPException(status_code=400, detail="Record is not locked")
    old_locked = r.locked_at.isoformat() if r.locked_at else None
    r.locked_at = None
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, {"locked_at": old_locked}, {"locked_at": None}, reason=body.reason)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.post("/settle", response_model=SettlementResponse)
def trigger_settlement(
    body: SettlementRequest = SettlementRequest(),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    result = run_daily_settlement(db, body.target_date)
    return result
