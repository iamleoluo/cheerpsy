from datetime import date, datetime, time, timezone
from decimal import Decimal

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.session_record import SessionRecord
from app.models.user import User
from app.schemas.session_record import (
    SessionRecordDirectEdit,
    SessionRecordResponse,
    SessionRecordUpdatePayment,
    DiscountRequest,
    OutcallBonusRequest,
    PayBatchRequest,
    PayRequest,
    SelfPayCaseStat,
    SettlementRequest,
    SettlementResponse,
    SplitRequest,
    VoidRequest,
)
from app.services.claim_batch import generate_batch_number
from app.services.pdf_generator import generate_self_pay_receipt
from app.services.settlement import materialize_due_appointments, run_daily_settlement

DEFAULT_COMMISSION_RATE = Decimal("0.70")


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


def _get_rate(r: SessionRecord, db: Session) -> Decimal:
    if r.commission_rate_used is not None:
        return Decimal(str(r.commission_rate_used))
    therapist = db.query(User).filter(User.id == r.therapist_id).first()
    if therapist and therapist.commission_rate is not None:
        return Decimal(str(therapist.commission_rate))
    return DEFAULT_COMMISSION_RATE


def _validate_and_set_payment(r: SessionRecord, method: str | None, note: str | None):
    if not method or method not in ("cash", "transfer"):
        raise HTTPException(status_code=400, detail="請選擇收款方式（現金或匯款）")
    r.payment_method = method
    if method == "transfer":
        if not note or not note.strip():
            raise HTTPException(status_code=400, detail="匯款資訊為必填（如帳戶末五碼）")
        r.payment_note = note.strip()
    else:
        r.payment_note = note.strip() if note else None


def _resolve_paid_at(paid_date: date | None) -> datetime:
    """If a collection date is supplied (back-dated entry), anchor at noon UTC to
    avoid timezone date-shift; otherwise use the current timestamp."""
    if paid_date is not None:
        return datetime.combine(paid_date, time(12, 0), tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _to_response(r: SessionRecord, db: Session) -> SessionRecordResponse:
    appt = r.appointment
    case = appt.case if appt else (db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None)
    therapist = appt.therapist if appt else db.query(User).filter(User.id == r.therapist_id).first()
    rate = _get_rate(r, db)
    amount = float(r.amount)
    discount = float(r.discount_amount or 0)
    effective = round(amount - discount, 2)
    bonus = float(r.outcall_bonus or 0)
    funding = r.funding_source or (case.funding_source if case else None)
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
        amount=amount,
        discount_amount=discount,
        discount_note=r.discount_note,
        effective_amount=effective,
        therapist_share=round(effective * float(rate) + bonus, 2),
        clinic_share=round(effective * float(1 - rate) - bonus, 2),
        payment_status=r.payment_status,
        funding_source=funding,
        institution_name=case.institution.name if case and case.institution else None,
        billing_cycle=case.billing_cycle if case else None,
        payment_method=r.payment_method,
        payment_note=r.payment_note,
        paid_at=r.paid_at,
        claim_number=r.claim_number,
        receipt_number=r.receipt_number,
        receipt_no=r.receipt_no,
        commission_rate_used=float(rate),
        claim_batch_id=r.claim_batch_id,
        claim_batch_number=r.claim_batch.batch_number if r.claim_batch else None,
        therapist_doc_submitted_at=r.therapist_doc_submitted_at,
        locked_at=r.locked_at,
        is_void=bool(r.is_void),
        void_reason=r.void_reason,
        parent_record_id=r.parent_record_id,
        outcall_bonus=float(r.outcall_bonus or 0),
        outcall_note=r.outcall_note,
    )


@router.get("", response_model=list[SessionRecordResponse])
def list_records(
    payment_status: str | None = Query(None),
    therapist_id: int | None = Query(None),
    month: str | None = Query(None, description="YYYY-MM"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import calendar
    materialize_due_appointments(db)
    query = db.query(SessionRecord).options(
        joinedload(SessionRecord.appointment).joinedload(Appointment.case).joinedload(Case.institution),
        joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
    )
    if user.role == "therapist":
        query = query.filter(SessionRecord.therapist_id == user.id)
    elif therapist_id:
        query = query.filter(SessionRecord.therapist_id == therapist_id)
    if payment_status:
        query = query.filter(SessionRecord.payment_status == payment_status)
    if month:
        try:
            year, mon = int(month[:4]), int(month[5:7])
            last_day = calendar.monthrange(year, mon)[1]
            query = query.filter(
                SessionRecord.session_date >= date(year, mon, 1),
                SessionRecord.session_date <= date(year, mon, last_day),
            )
        except (ValueError, IndexError):
            pass
    limit = None if month else 200
    q = query.order_by(SessionRecord.session_date.desc())
    records = (q.all() if limit is None else q.limit(limit).all())
    return [_to_response(r, db) for r in records]


@router.get("/pending-docs", response_model=list[SessionRecordResponse])
def list_pending_docs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Records inside a claim batch needing therapist doc confirmation.

    Scoped: therapist sees own; admin/staff/accountant see all.
    Not capped — pending docs may span multiple months.
    """
    materialize_due_appointments(db)
    q = db.query(SessionRecord).options(
        joinedload(SessionRecord.appointment).joinedload(Appointment.case).joinedload(Case.institution),
        joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
    ).filter(
        SessionRecord.claim_batch_id.isnot(None),
        SessionRecord.therapist_doc_submitted_at.is_(None),
    )
    if user.role == "therapist":
        q = q.filter(SessionRecord.therapist_id == user.id)
    records = q.order_by(SessionRecord.session_date.desc()).all()
    return [_to_response(r, db) for r in records]


@router.get("/confirmed-docs", response_model=list[SessionRecordResponse])
def list_confirmed_docs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Records whose therapist doc is already confirmed (for cancel-doc UI)."""
    q = db.query(SessionRecord).options(
        joinedload(SessionRecord.appointment).joinedload(Appointment.case).joinedload(Case.institution),
        joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
    ).filter(
        SessionRecord.claim_batch_id.isnot(None),
        SessionRecord.therapist_doc_submitted_at.isnot(None),
    )
    if user.role == "therapist":
        q = q.filter(SessionRecord.therapist_id == user.id)
    records = q.order_by(SessionRecord.therapist_doc_submitted_at.desc()).limit(200).all()
    return [_to_response(r, db) for r in records]


@router.get("/self-pay-unpaid", response_model=list[SessionRecordResponse])
def list_self_pay_unpaid(
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    """Self-pay records awaiting payment (no claim batch needed). Grouped by case client-side."""
    materialize_due_appointments(db)
    records = (
        db.query(SessionRecord)
        .options(
            joinedload(SessionRecord.appointment).joinedload(Appointment.case).joinedload(Case.institution),
            joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
        )
        .filter(
            SessionRecord.payment_status == "unpaid",
            SessionRecord.is_void.is_(False),
            SessionRecord.funding_source == "self_pay",
        )
        .order_by(SessionRecord.case_id, SessionRecord.session_date)
        .all()
    )
    return [_to_response(r, db) for r in records]


@router.get("/self-pay-all", response_model=list[SessionRecordResponse])
def list_self_pay_all(
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    """All non-void self-pay session records (paid + unpaid), for finance tracking."""
    materialize_due_appointments(db)
    records = (
        db.query(SessionRecord)
        .options(
            joinedload(SessionRecord.appointment).joinedload(Appointment.case).joinedload(Case.institution),
            joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
        )
        .filter(
            SessionRecord.is_void.is_(False),
            SessionRecord.funding_source == "self_pay",
        )
        .order_by(SessionRecord.session_date.desc(), SessionRecord.case_id)
        .all()
    )
    return [_to_response(r, db) for r in records]


@router.get("/self-pay-cases", response_model=list[SelfPayCaseStat])
def list_self_pay_cases(
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    """Aggregate all non-void self-pay session records by case, returning paid/unpaid counts."""
    from collections import defaultdict
    materialize_due_appointments(db)
    records = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.is_void.is_(False),
            SessionRecord.funding_source == "self_pay",
        )
        .order_by(SessionRecord.case_id, SessionRecord.session_date)
        .all()
    )

    groups: dict[int, list] = defaultdict(list)
    for r in records:
        groups[r.case_id or 0].append(r)

    result = []
    for case_id, recs in groups.items():
        case = db.query(Case).filter(Case.id == case_id).first() if case_id else None
        therapist = db.query(User).filter(User.id == case.therapist_id).first() if case else None

        def eff(r: SessionRecord) -> float:
            return float(r.amount) - float(r.discount_amount or 0)

        paid = [r for r in recs if r.payment_status in ("paid", "claimed")]
        unpaid = [r for r in recs if r.payment_status == "unpaid"]
        result.append(SelfPayCaseStat(
            case_id=case_id,
            case_name=case.name if case else f"#{case_id}",
            therapist_name=therapist.name if therapist else None,
            paid_count=len(paid),
            unpaid_count=len(unpaid),
            paid_amount=sum(eff(r) for r in paid),
            unpaid_amount=sum(eff(r) for r in unpaid),
            total_count=len(recs),
            all_paid=(len(unpaid) == 0 and len(recs) > 0),
        ))

    result.sort(key=lambda s: (s.all_paid, s.case_name))
    return result


def _build_receipt_dicts(records: list[SessionRecord], db: Session) -> list[dict]:
    out = []
    for r in records:
        appt = r.appointment
        therapist = appt.therapist if appt else db.query(User).filter(User.id == r.therapist_id).first()
        out.append({
            "session_date": r.session_date,
            "therapist_name": therapist.name if therapist else "",
            "session_type": {"in_person": "現場", "online": "線上", "outdoor": "外出"}.get(r.session_type, r.session_type),
            "amount": float(r.amount) - float(r.discount_amount or 0),
        })
    return out


@router.get("/receipt")
def download_combined_receipt(
    record_ids: str = Query(..., description="comma-separated session_record ids"),
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    ids = [int(x) for x in record_ids.split(",") if x.strip()]
    records = db.query(SessionRecord).filter(SessionRecord.id.in_(ids)).all()
    if not records:
        raise HTTPException(status_code=404, detail="No records found")
    records.sort(key=lambda r: (r.session_date, r.id))
    case = db.query(Case).filter(Case.id == records[0].case_id).first() if records[0].case_id else None
    dicts = _build_receipt_dicts(records, db)
    total = sum(d["amount"] for d in dicts)
    dates = sorted(r.session_date for r in records)
    label = f"R{dates[0].strftime('%Y%m%d')}-{len(records)}筆"
    pdf = generate_self_pay_receipt(
        batch_number=label,
        case_name=case.name if case else "N/A",
        period_start=dates[0],
        period_end=dates[-1],
        records=dicts,
        total_amount=total,
    )
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="receipt-{label}.pdf"'},
    )


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
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record is void")

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
    if body.payment_status in ("paid", "claimed") and r.paid_at is None:
        r.paid_at = datetime.now(timezone.utc)
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


@router.put("/{record_id}/edit", response_model=SessionRecordResponse)
def direct_edit_record(
    record_id: int,
    body: SessionRecordDirectEdit,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")

    valid_statuses = {"unpaid", "paid", "claiming", "claimed"}
    if body.payment_status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid payment status")

    before = {
        "payment_status": r.payment_status,
        "payment_method": r.payment_method,
        "payment_note": r.payment_note,
        "claim_number": r.claim_number,
        "receipt_number": r.receipt_number,
    }
    r.payment_status = body.payment_status
    r.payment_method = body.payment_method
    r.payment_note = body.payment_note.strip() if body.payment_note else None
    r.claim_number = body.claim_number.strip() if body.claim_number else None
    r.receipt_number = body.receipt_number.strip() if body.receipt_number else None
    after = {
        "payment_status": r.payment_status,
        "payment_method": r.payment_method,
        "payment_note": r.payment_note,
        "claim_number": r.claim_number,
        "receipt_number": r.receipt_number,
    }
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/confirm-doc", response_model=SessionRecordResponse)
def confirm_doc_submission(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if user.role == "therapist" and r.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Only the assigned therapist can confirm")
    if user.role not in ("therapist", "admin", "staff"):
        raise HTTPException(status_code=403, detail="Access denied")
    if r.therapist_doc_submitted_at:
        raise HTTPException(status_code=400, detail="Already confirmed")

    before = {
        "therapist_doc_submitted_at": None,
        "therapist_doc_submitted_by": None,
    }
    r.therapist_doc_submitted_at = datetime.now(timezone.utc)
    r.therapist_doc_submitted_by = user.id
    after = {
        "therapist_doc_submitted_at": r.therapist_doc_submitted_at.isoformat(),
        "therapist_doc_submitted_by": r.therapist_doc_submitted_by,
    }
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.flush()

    if r.claim_batch_id:
        batch = db.query(ClaimBatch).filter(ClaimBatch.id == r.claim_batch_id).first()
        if batch and batch.status == "collecting":
            unconfirmed = db.query(SessionRecord).filter(
                SessionRecord.claim_batch_id == batch.id,
                SessionRecord.therapist_doc_submitted_at.is_(None),
            ).count()
            if unconfirmed == 0:
                batch.status = "ready"

    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/cancel-doc", response_model=SessionRecordResponse)
def cancel_doc_submission(
    record_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.therapist_doc_submitted_at is None:
        raise HTTPException(status_code=400, detail="尚未確認")

    before = {
        "therapist_doc_submitted_at": r.therapist_doc_submitted_at.isoformat(),
        "therapist_doc_submitted_by": r.therapist_doc_submitted_by,
    }
    r.therapist_doc_submitted_at = None
    r.therapist_doc_submitted_by = None
    after = {
        "therapist_doc_submitted_at": None,
        "therapist_doc_submitted_by": None,
    }
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.flush()

    if r.claim_batch_id:
        batch = db.query(ClaimBatch).filter(ClaimBatch.id == r.claim_batch_id).first()
        if batch and batch.status == "ready":
            batch.status = "collecting"

    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/discount", response_model=SessionRecordResponse)
def set_discount(
    record_id: int,
    body: DiscountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record is void")
    if r.payment_status in ("paid", "claimed"):
        raise HTTPException(status_code=400, detail="已收款/已請款的紀錄不可調整優待")

    if user.role == "admin":
        pass
    elif user.role == "staff":
        if r.session_date != date.today():
            raise HTTPException(status_code=403, detail="行政人員僅能於當日調整優待，逾期請洽管理員")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    amount = Decimal(str(r.amount))
    if body.discount_percent is not None:
        pct = Decimal(str(body.discount_percent))
        if pct < 0 or pct > 100:
            raise HTTPException(status_code=400, detail="折扣百分比須介於 0~100")
        disc = (amount * pct / Decimal("100")).quantize(Decimal("0.01"))
    elif body.discount_amount is not None:
        disc = Decimal(str(body.discount_amount)).quantize(Decimal("0.01"))
    else:
        disc = Decimal("0")
    if disc < 0 or disc > amount:
        raise HTTPException(status_code=400, detail="優待金額須介於 0 ~ 原始金額")

    before = {"discount_amount": float(r.discount_amount or 0), "discount_note": r.discount_note}
    r.discount_amount = disc
    r.discount_note = body.discount_note.strip() if body.discount_note else None
    after = {"discount_amount": float(disc), "discount_note": r.discount_note}
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/void", response_model=SessionRecordResponse)
def void_record(
    record_id: int,
    body: VoidRequest = VoidRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record already void")
    if r.payment_status in ("paid", "claimed"):
        raise HTTPException(status_code=400, detail="已收款/已請款的紀錄不可作廢")

    if user.role == "therapist":
        if r.therapist_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if r.session_date != date.today():
            raise HTTPException(status_code=403, detail="心理師僅能於當日作廢，逾期請洽管理員")
    elif user.role in ("admin", "staff"):
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    before = {"is_void": r.is_void, "payment_status": r.payment_status}
    r.is_void = True
    r.void_reason = body.reason.strip() if body.reason else None
    r.voided_at = datetime.now(timezone.utc)
    r.voided_by = user.id
    after = {"is_void": r.is_void, "void_reason": r.void_reason}
    _write_audit(db, "session_records", r.id, "VOID", user.id, before, after, reason=r.void_reason)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.post("/{record_id}/split", response_model=list[SessionRecordResponse])
def split_record(
    record_id: int,
    body: SplitRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """Split a machine-fundable record: take `self_pay_amount` off the institution
    record and create a paid self-pay sibling. Receipt no gets -A/-B suffixes.
    """
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record is void")
    if r.parent_record_id is not None:
        raise HTTPException(status_code=400, detail="拆帳子紀錄不可再拆")
    if (r.funding_source or "self_pay") != "institution":
        raise HTTPException(status_code=400, detail="僅機構款可拆帳")
    if r.locked_at is not None:
        raise HTTPException(status_code=400, detail="已鎖定的紀錄不可拆帳")
    if r.claim_batch_id:
        batch = db.query(ClaimBatch).filter(ClaimBatch.id == r.claim_batch_id).first()
        if batch and batch.status not in ("collecting", "ready"):
            raise HTTPException(status_code=400, detail=f"批次狀態為「{batch.status}」，不可拆帳")
    if body.self_pay_amount <= 0:
        raise HTTPException(status_code=400, detail="自費金額需大於 0")
    full = float(r.amount)
    if body.self_pay_amount >= full:
        raise HTTPException(status_code=400, detail=f"自費金額需小於原金額 {full}")
    if body.payment_method not in ("cash", "transfer"):
        raise HTTPException(status_code=400, detail="付款方式僅支援現金或匯款")

    # Adjust original (institution side) — append -A suffix if not already
    before = {
        "amount": full,
        "receipt_no": r.receipt_no,
    }
    inst_amount = round(full - body.self_pay_amount, 2)
    original_receipt = r.receipt_no
    r.amount = inst_amount
    if r.receipt_no and not r.receipt_no.endswith("-A"):
        r.receipt_no = f"{r.receipt_no}-A"

    # Build self-pay child
    child = SessionRecord(
        appointment_id=None,  # split doesn't reuse appointment unique constraint
        invoice_id=None,
        session_date=r.session_date,
        case_id=r.case_id,
        therapist_id=r.therapist_id,
        session_type=r.session_type,
        room_id=r.room_id,
        fee_category=body.fee_category,
        amount=body.self_pay_amount,
        commission_rate_used=r.commission_rate_used,
        funding_source="self_pay",
        payment_status="paid",
        payment_method=body.payment_method,
        payment_note=body.payment_note,
        paid_at=datetime.now(timezone.utc),
        parent_record_id=r.id,
        receipt_no=f"{original_receipt}-B" if original_receipt else None,
        created_by=user.id,
    )
    db.add(child)
    db.flush()

    _write_audit(
        db, "session_records", r.id, "SPLIT", user.id,
        before,
        {
            "amount": float(r.amount),
            "receipt_no": r.receipt_no,
            "child_id": child.id,
            "child_amount": body.self_pay_amount,
        },
    )
    db.commit()
    db.refresh(r)
    db.refresh(child)
    return [_to_response(r, db), _to_response(child, db)]


@router.put("/{record_id}/outcall-bonus", response_model=SessionRecordResponse)
def set_outcall_bonus(
    record_id: int,
    body: OutcallBonusRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """Set or clear the outcall bonus (default 1000) for a record.

    `amount=0` clears it. Staff can only modify same-day records.
    """
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record is void")
    if r.locked_at is not None:
        raise HTTPException(status_code=400, detail="已鎖定的紀錄不可調整保底")
    if body.amount < 0:
        raise HTTPException(status_code=400, detail="保底金額不可為負")
    if user.role == "staff" and r.session_date != date.today():
        raise HTTPException(status_code=403, detail="行政人員僅能於當日調整保底，逾期請洽管理員")

    before = {"outcall_bonus": float(r.outcall_bonus or 0), "outcall_note": r.outcall_note}
    r.outcall_bonus = body.amount
    r.outcall_note = body.note.strip() if body.note else None
    _write_audit(
        db, "session_records", r.id, "UPDATE", user.id,
        before,
        {"outcall_bonus": float(r.outcall_bonus), "outcall_note": r.outcall_note},
    )
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.put("/{record_id}/pay", response_model=SessionRecordResponse)
def pay_self_pay_record(
    record_id: int,
    body: PayRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.is_void:
        raise HTTPException(status_code=400, detail="Record is void")
    if r.payment_status != "unpaid":
        raise HTTPException(status_code=400, detail="僅未收款的紀錄可付款")
    if (r.funding_source or "self_pay") != "self_pay":
        raise HTTPException(status_code=400, detail="此功能僅適用自費紀錄")
    before = {"payment_status": r.payment_status, "payment_method": r.payment_method}
    _validate_and_set_payment(r, body.payment_method, body.payment_note)
    r.payment_status = "paid"
    r.paid_at = _resolve_paid_at(body.paid_date)
    after = {"payment_status": r.payment_status, "payment_method": r.payment_method}
    _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(r)
    return _to_response(r, db)


@router.post("/pay-batch")
def pay_batch(
    body: PayBatchRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    if not body.record_ids:
        raise HTTPException(status_code=400, detail="未選擇任何紀錄")
    records = db.query(SessionRecord).filter(SessionRecord.id.in_(body.record_ids)).all()
    if len(records) != len(set(body.record_ids)):
        raise HTTPException(status_code=400, detail="部分紀錄不存在")
    for r in records:
        if r.is_void:
            raise HTTPException(status_code=400, detail=f"紀錄 {r.id} 已作廢")
        if r.payment_status != "unpaid":
            raise HTTPException(status_code=400, detail=f"紀錄 {r.id} 非未收款狀態")
        if (r.funding_source or "self_pay") != "self_pay":
            raise HTTPException(status_code=400, detail=f"紀錄 {r.id} 非自費")
    paid_at = _resolve_paid_at(body.paid_date)
    for r in records:
        before = {"payment_status": r.payment_status}
        _validate_and_set_payment(r, body.payment_method, body.payment_note)
        r.payment_status = "paid"
        r.paid_at = paid_at
        _write_audit(db, "session_records", r.id, "UPDATE", user.id, before, {"payment_status": "paid"})

    # Create a ClaimBatch for combined receipt when multiple records
    batch_id: int | None = None
    if body.combine_receipt and len(records) > 1:
        case_id = records[0].case_id
        case = db.query(Case).filter(Case.id == case_id).first() if case_id else None
        period_start = paid_at.date() if paid_at else date.today()
        batch_number = generate_batch_number(db, "self_pay", case, None, period_start)
        batch = ClaimBatch(
            batch_number=batch_number,
            type="self_pay",
            case_id=case_id,
            total_amount=sum(float(r.amount) for r in records),
            payment_method=body.payment_method,
            payment_note=body.payment_note,
            status="closed",
            closed_at=paid_at,
            created_by=user.id,
        )
        db.add(batch)
        db.flush()
        for r in records:
            r.claim_batch_id = batch.id
        batch_id = batch.id

    db.commit()
    return {
        "paid": len(records),
        "record_ids": [r.id for r in records],
        "combine_receipt": body.combine_receipt,
        "batch_id": batch_id,
    }



@router.post("/settle", response_model=SettlementResponse)
def trigger_settlement(
    body: SettlementRequest = SettlementRequest(),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    if body.date_from and body.date_to:
        total_executed = 0
        total_skipped = 0
        d = body.date_from
        while d <= body.date_to:
            r = run_daily_settlement(db, d)
            total_executed += r["executed"]
            total_skipped += r["skipped"]
            d += timedelta(days=1)
        return {"date": f"{body.date_from} ~ {body.date_to}", "executed": total_executed, "skipped": total_skipped}
    result = run_daily_settlement(db, body.target_date)
    return result
