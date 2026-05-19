from datetime import datetime

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.institution import Institution
from app.models.session_record import SessionRecord


def generate_batch_number(db: Session, batch_type: str, case: Case | None, institution: Institution | None, period_start) -> str:
    """
    Self-pay:    S{cycle_code}-{case_number}-{YYYYMM}
    Institution: I-{institution.code}-{YYYYMM}
    """
    yyyymm = period_start.strftime("%Y%m") if period_start else datetime.now().strftime("%Y%m")

    if batch_type == "institution" and institution:
        code = institution.code or str(institution.id)
        base = f"I-{code}-{yyyymm}"
    elif case:
        cycle_map = {"once": "O", "monthly": "M", "multiple": "X"}
        cycle_code = cycle_map.get(case.billing_cycle or "once", "O")
        case_num = case.case_number or f"T{case.temp_seq or case.id}"
        base = f"S{cycle_code}-{case_num}-{yyyymm}"
    else:
        base = f"S-UNKNOWN-{yyyymm}"

    existing = db.query(ClaimBatch).filter(ClaimBatch.batch_number.like(f"{base}%")).count()
    if existing > 0:
        return f"{base}-{existing + 1}"
    return base


def recalculate_total(db: Session, batch_id: int) -> float:
    records = db.query(SessionRecord).filter(SessionRecord.claim_batch_id == batch_id).all()
    total = sum(float(r.amount) for r in records)
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if batch:
        batch.total_amount = total
    return total


def _resolve_institution(db: Session, batch: ClaimBatch) -> Institution | None:
    if batch.institution_id:
        return db.query(Institution).filter(Institution.id == batch.institution_id).first()
    if batch.case_id:
        case = db.query(Case).filter(Case.id == batch.case_id).first()
        if case and case.institution_id:
            return db.query(Institution).filter(Institution.id == case.institution_id).first()
    return None


def docs_required(db: Session, batch: ClaimBatch) -> bool:
    """Whether therapist docs gate this batch's readiness."""
    if batch.docs_waived_at is not None:
        return False
    inst = _resolve_institution(db, batch)
    if inst is not None and inst.requires_therapist_docs is False:
        return False
    return True


def check_readiness(db: Session, batch_id: int) -> bool:
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        return False
    records = db.query(SessionRecord).filter(SessionRecord.claim_batch_id == batch_id).all()
    if not records:
        return False
    if not docs_required(db, batch):
        return True
    return all(r.therapist_doc_submitted_at is not None for r in records)


def auto_transition_to_ready(db: Session, batch_id: int):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch or batch.status != "collecting":
        return
    if check_readiness(db, batch_id):
        batch.status = "ready"
