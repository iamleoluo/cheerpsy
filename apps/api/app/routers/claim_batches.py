import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.claim_batch import ClaimBatch
from app.models.institution import Institution
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit
from app.schemas.claim_batch import (
    ClaimBatchCreate,
    ClaimBatchRecordResponse,
    ClaimBatchResponse,
    ClaimBatchUpdate,
)
from app.services.claim_batch import (
    apply_doc_waiver,
    auto_transition_to_ready,
    check_readiness,
    docs_required,
    generate_batch_number,
    recalculate_total,
    revert_doc_waiver,
)
from app.services.pdf_generator import (
    generate_institution_claim_form,
    generate_self_pay_receipt,
)
from app.services.pdf import generate_pdf, render_multi

router = APIRouter(prefix="/claim-batches", tags=["claim-batches"])


def _to_response(db: Session, b: ClaimBatch) -> ClaimBatchResponse:
    records = db.query(SessionRecord).filter(SessionRecord.claim_batch_id == b.id).all()
    record_count = len(records)
    confirmed_count = sum(1 for r in records if r.therapist_doc_submitted_at is not None)

    case_name = None
    if b.case_id:
        case = db.query(Case).filter(Case.id == b.case_id).first()
        if case:
            case_name = case.name

    inst_name = None
    if b.institution_id:
        inst = db.query(Institution).filter(Institution.id == b.institution_id).first()
        if inst:
            inst_name = inst.name

    return ClaimBatchResponse(
        id=b.id,
        batch_number=b.batch_number,
        external_ref=b.external_ref,
        type=b.type,
        billing_cycle=b.billing_cycle,
        expected_sessions=b.expected_sessions,
        institution_id=b.institution_id,
        institution_name=inst_name,
        case_id=b.case_id,
        case_name=case_name,
        period_start=b.period_start,
        period_end=b.period_end,
        total_amount=float(b.total_amount or 0),
        payment_method=b.payment_method,
        payment_note=b.payment_note,
        status=b.status,
        record_count=record_count,
        confirmed_count=confirmed_count,
        created_at=b.created_at.isoformat() if b.created_at else None,
        submitted_at=b.submitted_at.isoformat() if b.submitted_at else None,
        received_at=b.received_at.isoformat() if b.received_at else None,
        closed_at=b.closed_at.isoformat() if b.closed_at else None,
        docs_waived_at=b.docs_waived_at,
        docs_waived_by=b.docs_waived_by,
        docs_required=docs_required(db, b),
    )


@router.get("", response_model=list[ClaimBatchResponse])
def list_claim_batches(
    status: str | None = Query(None),
    case_id: int | None = Query(None),
    institution_id: int | None = Query(None),
    batch_type: str | None = Query(None, alias="type"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ClaimBatch)
    if status:
        q = q.filter(ClaimBatch.status == status)
    if case_id:
        q = q.filter(ClaimBatch.case_id == case_id)
    if institution_id:
        q = q.filter(ClaimBatch.institution_id == institution_id)
    if batch_type:
        q = q.filter(ClaimBatch.type == batch_type)
    batches = q.order_by(ClaimBatch.created_at.desc()).all()
    return [_to_response(db, b) for b in batches]


@router.get("/eligible-cases")
def list_eligible_cases(
    type: str = Query("self_pay", description="self_pay or institution"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return cases that have unassigned session_records, filtered by record funding_source."""
    from sqlalchemy import distinct

    # Filter by SessionRecord.funding_source (not Case.funding_source) —
    # a case may be "self_pay" overall but have individual institution-funded records (split-pay).
    q = (
        db.query(distinct(SessionRecord.case_id))
        .filter(
            SessionRecord.claim_batch_id.is_(None),
            SessionRecord.case_id.isnot(None),
            SessionRecord.is_void.is_(False),
        )
    )
    if type == "self_pay":
        q = q.filter(SessionRecord.funding_source == "self_pay")
    elif type == "institution":
        q = q.filter(SessionRecord.funding_source == "institution")

    cids = [row[0] for row in q.all()]
    if not cids:
        return []

    cases = db.query(Case).filter(Case.id.in_(cids)).order_by(Case.name).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "case_number": c.case_number,
            "billing_cycle": c.billing_cycle,
            "funding_source": c.funding_source,
            "institution_id": c.institution_id,
        }
        for c in cases
    ]


@router.get("/eligible-institutions")
def list_eligible_institutions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return institutions with unassigned institution-funded session_records.

    Institution lookup walks two paths:
    1. case.institution_id (standard institution case)
    2. appointment → quota → institution_id (split-pay / partial institution case)
    """
    records = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.claim_batch_id.is_(None),
            SessionRecord.is_void.is_(False),
            SessionRecord.funding_source == "institution",
        )
        .all()
    )
    if not records:
        return []

    iids: set[int] = set()
    for r in records:
        # Path 1: case.institution_id
        if r.case_id:
            case = db.query(Case).filter(Case.id == r.case_id).first()
            if case and case.institution_id:
                iids.add(case.institution_id)
        # Path 2: appointment → quota → institution_id
        if r.appointment_id:
            appt = db.query(Appointment).filter(Appointment.id == r.appointment_id).first()
            if appt and appt.quota_id:
                quota = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == appt.quota_id).first()
                if quota and quota.institution_id:
                    iids.add(quota.institution_id)

    if not iids:
        return []

    institutions = db.query(Institution).filter(Institution.id.in_(iids)).order_by(Institution.name).all()
    return [{"id": i.id, "name": i.name, "code": i.code} for i in institutions]


@router.get("/unassigned/records")
def list_unassigned_records(
    case_id: int | None = Query(None),
    institution_id: int | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(SessionRecord).filter(
        SessionRecord.claim_batch_id.is_(None),
        SessionRecord.is_void.is_(False),
    )

    if case_id:
        q = q.filter(SessionRecord.case_id == case_id)
    elif institution_id:
        # Path 1: case.institution_id (standard institution case)
        case_ids = set(c.id for c in db.query(Case).filter(Case.institution_id == institution_id).all())
        # Path 2: appointment → quota → institution_id (split-pay / partial institution)
        quota_case_ids = set(
            row[0]
            for row in db.query(SessionRecord.case_id)
            .join(Appointment, Appointment.id == SessionRecord.appointment_id)
            .join(CaseInstitutionQuota, CaseInstitutionQuota.id == Appointment.quota_id)
            .filter(
                CaseInstitutionQuota.institution_id == institution_id,
                SessionRecord.claim_batch_id.is_(None),
                SessionRecord.is_void.is_(False),
                SessionRecord.funding_source == "institution",
            )
            .all()
        )
        case_ids |= quota_case_ids
        if case_ids:
            q = q.filter(SessionRecord.case_id.in_(case_ids), SessionRecord.funding_source == "institution")
        else:
            return []

    records = q.order_by(SessionRecord.session_date.desc()).all()
    result = []
    for r in records:
        case = db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None
        therapist = db.query(User).filter(User.id == r.therapist_id).first()
        result.append({
            "id": r.id,
            "session_date": r.session_date.isoformat(),
            "case_id": r.case_id,
            "case_name": case.name if case else None,
            "therapist_name": therapist.name if therapist else None,
            "session_type": r.session_type,
            "amount": float(r.amount),
            "payment_status": r.payment_status,
            "therapist_doc_submitted_at": r.therapist_doc_submitted_at.isoformat() if r.therapist_doc_submitted_at else None,
        })
    return result


@router.get("/{batch_id}", response_model=ClaimBatchResponse)
def get_claim_batch(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    return _to_response(db, batch)


@router.get("/{batch_id}/records", response_model=list[ClaimBatchRecordResponse])
def get_batch_records(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")

    records = (
        db.query(SessionRecord)
        .filter(SessionRecord.claim_batch_id == batch_id)
        .order_by(SessionRecord.session_date)
        .all()
    )
    result = []
    for r in records:
        case = db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None
        therapist = db.query(User).filter(User.id == r.therapist_id).first()
        result.append(ClaimBatchRecordResponse(
            id=r.id,
            session_date=r.session_date.isoformat(),
            case_name=case.name if case else None,
            therapist_name=therapist.name if therapist else None,
            session_type=r.session_type,
            amount=float(r.amount),
            payment_status=r.payment_status,
            therapist_doc_submitted_at=r.therapist_doc_submitted_at.isoformat() if r.therapist_doc_submitted_at else None,
        ))
    return result


@router.post("", response_model=ClaimBatchResponse)
def create_claim_batch(
    body: ClaimBatchCreate,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    if body.type not in ("self_pay", "institution"):
        raise HTTPException(status_code=400, detail="type must be self_pay or institution")

    if body.type == "institution" and not body.institution_id:
        raise HTTPException(status_code=400, detail="institution_id required for institution type")
    if body.type == "self_pay" and not body.case_id:
        raise HTTPException(status_code=400, detail="case_id required for self_pay type")

    case = db.query(Case).filter(Case.id == body.case_id).first() if body.case_id else None
    institution = db.query(Institution).filter(Institution.id == body.institution_id).first() if body.institution_id else None

    # Validate records aren't already assigned to another batch
    for rid in body.session_record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == rid).first()
        if not sr:
            raise HTTPException(status_code=400, detail=f"Session record {rid} not found")
        if sr.claim_batch_id is not None:
            raise HTTPException(status_code=400, detail=f"Session record {rid} already belongs to batch {sr.claim_batch_id}")

    batch_number = generate_batch_number(db, body.type, case, institution, body.period_start)

    batch = ClaimBatch(
        batch_number=batch_number,
        type=body.type,
        billing_cycle=body.billing_cycle or (case.billing_cycle if case else None),
        expected_sessions=len(body.session_record_ids) or None,
        institution_id=body.institution_id,
        case_id=body.case_id,
        period_start=body.period_start,
        period_end=body.period_end,
        status="collecting",
        created_by=user.id,
    )
    db.add(batch)
    db.flush()

    for rid in body.session_record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == rid).first()
        sr.claim_batch_id = batch.id

    recalculate_total(db, batch.id)
    # Institution that doesn't require docs → waive every record up front so no
    # per-record confirmation request blocks payment.
    if not docs_required(db, batch):
        from datetime import datetime, timezone
        apply_doc_waiver(db, batch, user.id, datetime.now(timezone.utc))
        db.flush()
    auto_transition_to_ready(db, batch.id)
    db.commit()
    db.refresh(batch)
    return _to_response(db, batch)


@router.put("/{batch_id}", response_model=ClaimBatchResponse)
def update_claim_batch(
    batch_id: int,
    body: ClaimBatchUpdate,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")

    before = {"external_ref": batch.external_ref, "payment_method": batch.payment_method, "payment_note": batch.payment_note}
    if body.external_ref is not None:
        batch.external_ref = body.external_ref
    if body.payment_method is not None:
        batch.payment_method = body.payment_method
    if body.payment_note is not None:
        batch.payment_note = body.payment_note
    after = {"external_ref": batch.external_ref, "payment_method": batch.payment_method, "payment_note": batch.payment_note}
    write_audit(db, "claim_batches", batch.id, "UPDATE", user.id, before, after)

    db.commit()
    db.refresh(batch)
    return _to_response(db, batch)


@router.post("/{batch_id}/records")
def add_records_to_batch(
    batch_id: int,
    record_ids: list[int],
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    if batch.status not in ("collecting", "ready"):
        raise HTTPException(status_code=400, detail=f"Cannot add records to batch in status '{batch.status}'")

    added = 0
    for rid in record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == rid).first()
        if not sr:
            raise HTTPException(status_code=400, detail=f"Session record {rid} not found")
        if sr.claim_batch_id is not None and sr.claim_batch_id != batch_id:
            raise HTTPException(status_code=400, detail=f"Session record {rid} already belongs to another batch")
        if sr.claim_batch_id != batch_id:
            sr.claim_batch_id = batch_id
            added += 1

    recalculate_total(db, batch_id)
    batch.status = "collecting"
    if not docs_required(db, batch):
        from datetime import datetime, timezone
        apply_doc_waiver(db, batch, user.id, datetime.now(timezone.utc))
        db.flush()
    auto_transition_to_ready(db, batch_id)
    db.commit()
    return {"added": added}


@router.delete("/{batch_id}/records/{record_id}")
def remove_record_from_batch(
    batch_id: int,
    record_id: int,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    if batch.status not in ("collecting", "ready"):
        raise HTTPException(status_code=400, detail=f"Cannot remove records from batch in status '{batch.status}'")

    sr = db.query(SessionRecord).filter(SessionRecord.id == record_id, SessionRecord.claim_batch_id == batch_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail="Record not in this batch")

    sr.claim_batch_id = None
    recalculate_total(db, batch_id)
    batch.status = "collecting"
    auto_transition_to_ready(db, batch_id)
    db.commit()
    return {"removed": record_id}


# ── State transitions ──

@router.put("/{batch_id}/submit")
def submit_batch(
    batch_id: int,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")

    if batch.type == "institution" and batch.status != "ready":
        raise HTTPException(status_code=400, detail="Institution batch must be in 'ready' status to submit")
    if batch.type == "self_pay" and batch.status not in ("collecting", "ready"):
        raise HTTPException(status_code=400, detail="Self-pay batch must be in 'collecting' or 'ready' status to submit")

    from datetime import datetime, timezone
    old_status = batch.status
    batch.status = "submitted"
    batch.submitted_at = datetime.now(timezone.utc)
    write_audit(db, "claim_batches", batch.id, "UPDATE", user.id,
                {"status": old_status}, {"status": "submitted"})
    db.commit()
    return {"status": "submitted"}


@router.put("/{batch_id}/receive")
def receive_batch(
    batch_id: int,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    if batch.type != "institution":
        raise HTTPException(status_code=400, detail="Only institution batches can be received")
    if batch.status != "submitted":
        raise HTTPException(status_code=400, detail="Batch must be in 'submitted' status")

    from datetime import datetime, timezone
    batch.status = "received"
    batch.received_at = datetime.now(timezone.utc)
    write_audit(db, "claim_batches", batch.id, "UPDATE", user.id,
                {"status": "submitted"}, {"status": "received"})
    records = db.query(SessionRecord).filter(SessionRecord.claim_batch_id == batch_id).all()
    for r in records:
        if r.payment_status in ("unpaid", "claiming"):
            r.payment_status = "claimed"
    db.commit()
    return {"status": "received"}


@router.put("/{batch_id}/waive-docs", response_model=ClaimBatchResponse)
def waive_docs(
    batch_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    if batch.type != "institution":
        raise HTTPException(status_code=400, detail="Only institution batches can waive docs")

    from datetime import datetime, timezone
    batch.docs_waived_at = datetime.now(timezone.utc)
    batch.docs_waived_by = user.id
    db.flush()
    # Write the waiver onto every record so per-record doc requests disappear
    waived = apply_doc_waiver(db, batch, user.id, batch.docs_waived_at)
    db.flush()
    auto_transition_to_ready(db, batch.id)
    write_audit(db, "claim_batches", batch.id, "WAIVE_DOCS", user.id,
                {"docs_waived_at": None},
                {"docs_waived_at": batch.docs_waived_at.isoformat(), "records_waived": waived})
    db.commit()
    db.refresh(batch)
    return _to_response(db, batch)


@router.put("/{batch_id}/unwaive-docs", response_model=ClaimBatchResponse)
def unwaive_docs(
    batch_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")

    before = {"docs_waived_at": batch.docs_waived_at.isoformat() if batch.docs_waived_at else None}
    old_at = batch.docs_waived_at
    old_by = batch.docs_waived_by
    batch.docs_waived_at = None
    batch.docs_waived_by = None
    # Undo only the records auto-confirmed by this exact waiver
    reverted = revert_doc_waiver(db, batch, old_at, old_by)
    db.flush()
    if batch.status == "ready" and not check_readiness(db, batch.id):
        batch.status = "collecting"
    write_audit(db, "claim_batches", batch.id, "UNWAIVE_DOCS", user.id,
                before, {"docs_waived_at": None, "records_reverted": reverted})
    db.commit()
    db.refresh(batch)
    return _to_response(db, batch)


# ── Attendance sheet PDF preview (no DB required) ──

@router.get("/attendance-sheet/preview")
def preview_attendance_sheet(
    template: str = Query("jiafuzongxin_attendance", description="jiafuzongxin_attendance | jiafangzhongxin_attendance"),
    pages: int = Query(2, ge=1, le=5, description="How many fake case pages to generate"),
    user: User = Depends(get_current_user),
):
    """Generate a sample attendance sheet PDF with fake data — for layout testing."""
    from datetime import date
    from app.services.pdf.templates import TEMPLATES

    if template not in ("jiafuzongxin_attendance", "jiafangzhongxin_attendance"):
        raise HTTPException(status_code=400, detail=f"Unknown template: {template!r}. Use jiafuzongxin_attendance or jiafangzhongxin_attendance")

    builder = TEMPLATES[template]

    fake_cases = [
        {"case_name": "王小明", "case_number": "26000101", "therapist_name": "陳怡君 心理師",
         "social_worker": "林美惠社工", "referral_unit": "南台南家扶中心"},
        {"case_name": "李小花", "case_number": "26000102", "therapist_name": "張文雄 心理師",
         "social_worker": "", "referral_unit": ""},
        {"case_name": "黃大偉", "case_number": "26000103", "therapist_name": "陳怡君 心理師",
         "social_worker": "劉志明社工", "referral_unit": ""},
        {"case_name": "林小芳", "case_number": "26000104", "therapist_name": "周麗華 心理師",
         "social_worker": "", "referral_unit": ""},
        {"case_name": "吳建國", "case_number": "26000105", "therapist_name": "張文雄 心理師",
         "social_worker": "陳美玲社工", "referral_unit": ""},
    ]

    fake_sessions = [
        {"session_date": date(2026, 3, 5), "time_str": "14:00"},
        {"session_date": date(2026, 3, 12), "time_str": "14:00"},
        {"session_date": date(2026, 3, 19), "time_str": "14:00"},
        {"session_date": date(2026, 4, 2),  "time_str": "14:00"},
        {"session_date": date(2026, 4, 9),  "time_str": "15:30"},
    ]

    specs = []
    for i in range(min(pages, len(fake_cases))):
        c = fake_cases[i]
        data = {
            "case_name": c["case_name"],
            "case_number": c["case_number"],
            "therapist_name": c["therapist_name"],
            "social_worker": c.get("social_worker", ""),
            "referral_unit": c.get("referral_unit", ""),
            "records": fake_sessions[:3 + i],  # vary session count per case
        }
        specs.append(builder(data))

    pdf_bytes = render_multi(specs)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="attendance-preview-{template}.pdf"'},
    )


# ── PDF download ──

def _build_record_dicts(db: Session, batch_id: int) -> list[dict]:
    records = (
        db.query(SessionRecord)
        .filter(SessionRecord.claim_batch_id == batch_id)
        .order_by(SessionRecord.session_date)
        .all()
    )
    result = []
    for r in records:
        case = db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None
        therapist = db.query(User).filter(User.id == r.therapist_id).first()
        result.append({
            "session_date": r.session_date,
            "case_name": case.name if case else "",
            "therapist_name": therapist.name if therapist else "",
            "session_type": r.session_type,
            "amount": float(r.amount),
        })
    return result



@router.get("/{batch_id}/claim-form")
def download_claim_form(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    if batch.type != "institution":
        raise HTTPException(status_code=400, detail="Claim forms are for institution batches only")

    inst = db.query(Institution).filter(Institution.id == batch.institution_id).first() if batch.institution_id else None
    records = _build_record_dicts(db, batch_id)

    pdf_bytes = generate_institution_claim_form(
        batch_number=batch.batch_number,
        institution_name=inst.name if inst else "N/A",
        period_start=batch.period_start,
        period_end=batch.period_end,
        records=records,
        total_amount=float(batch.total_amount or 0),
        external_ref=batch.external_ref,
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="claim-{batch.batch_number}.pdf"'},
    )


