from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution import Institution
from app.models.user import User
from app.schemas.case_quota import QuotaCreate, QuotaResponse, QuotaUpdate
from app.services.audit import write_audit

router = APIRouter(tags=["case-quotas"])

WRITE_ROLES = ["admin", "staff"]


def _to_response(q: CaseInstitutionQuota, db: Session) -> QuotaResponse:
    reserved = db.query(Appointment).filter(
        Appointment.quota_id == q.id,
        Appointment.status == "booked",
    ).count()
    return QuotaResponse(
        id=q.id,
        case_id=q.case_id,
        case_name=q.case.name if q.case else None,
        institution_id=q.institution_id,
        institution_name=q.institution.name if q.institution else None,
        total_count=q.total_count,
        used_count=q.used_count,
        reserved_count=reserved,
        remaining=q.total_count - q.used_count - reserved,
        valid_from=q.valid_from,
        valid_until=q.valid_until,
        note=q.note,
    )


@router.get("/cases/{case_id}/quotas", response_model=list[QuotaResponse])
def list_case_quotas(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not db.query(Case).filter(Case.id == case_id).first():
        raise HTTPException(status_code=404, detail="個案不存在")
    rows = (
        db.query(CaseInstitutionQuota)
        .filter(CaseInstitutionQuota.case_id == case_id)
        .order_by(CaseInstitutionQuota.valid_until.asc(), CaseInstitutionQuota.id.asc())
        .all()
    )
    return [_to_response(q, db) for q in rows]


@router.get("/cases/{case_id}/quotas/available", response_model=list[QuotaResponse])
def list_available_quotas(
    case_id: int,
    institution_id: int | None = Query(None),
    on_date: date | None = Query(None, description="預約日；預設今日"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """有效 Quota：valid_from ≤ on_date ≤ valid_until 且剩餘 > 0；依 valid_until 升冪（FIFO）。"""
    target = on_date or date.today()
    q = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            CaseInstitutionQuota.valid_from <= target,
            CaseInstitutionQuota.valid_until >= target,
            CaseInstitutionQuota.used_count < CaseInstitutionQuota.total_count,
        )
    )
    if institution_id is not None:
        q = q.filter(CaseInstitutionQuota.institution_id == institution_id)
    rows = q.order_by(CaseInstitutionQuota.valid_until.asc(), CaseInstitutionQuota.id.asc()).all()
    return [_to_response(r, db) for r in rows]


@router.get("/quotas", response_model=list[QuotaResponse])
def list_all_quotas(
    active_only: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跨個案列表，供「機構額度」分頁使用。"""
    q = db.query(CaseInstitutionQuota)
    if active_only:
        today = date.today()
        q = q.filter(
            CaseInstitutionQuota.valid_from <= today,
            CaseInstitutionQuota.valid_until >= today,
            CaseInstitutionQuota.used_count < CaseInstitutionQuota.total_count,
        )
    rows = q.order_by(CaseInstitutionQuota.valid_until.asc(), CaseInstitutionQuota.id.desc()).all()
    return [_to_response(r, db) for r in rows]


@router.post("/cases/{case_id}/quotas", response_model=QuotaResponse, status_code=201)
def create_quota(
    case_id: int,
    body: QuotaCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    if not db.query(Case).filter(Case.id == case_id).first():
        raise HTTPException(status_code=404, detail="個案不存在")
    if not db.query(Institution).filter(Institution.id == body.institution_id).first():
        raise HTTPException(status_code=404, detail="機構不存在")
    if body.total_count <= 0:
        raise HTTPException(status_code=400, detail="總次數需大於 0")
    if body.valid_from > body.valid_until:
        raise HTTPException(status_code=400, detail="有效起日不可晚於迄日")

    q = CaseInstitutionQuota(
        case_id=case_id,
        institution_id=body.institution_id,
        total_count=body.total_count,
        used_count=0,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        note=body.note,
        created_by=user.id,
    )
    db.add(q)
    db.flush()
    write_audit(
        db, "case_institution_quotas", q.id, "CREATE", user.id,
        None,
        {
            "case_id": case_id,
            "institution_id": body.institution_id,
            "total_count": body.total_count,
            "valid_from": str(body.valid_from),
            "valid_until": str(body.valid_until),
        },
    )
    db.commit()
    db.refresh(q)
    return _to_response(q, db)


@router.put("/quotas/{quota_id}", response_model=QuotaResponse)
def update_quota(
    quota_id: int,
    body: QuotaUpdate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quota 不存在")

    before = {
        "total_count": q.total_count,
        "valid_from": str(q.valid_from),
        "valid_until": str(q.valid_until),
        "note": q.note,
    }
    if body.total_count is not None:
        if body.total_count < q.used_count:
            raise HTTPException(status_code=400, detail=f"總次數不可少於已用次數 {q.used_count}")
        q.total_count = body.total_count
    if body.valid_from is not None:
        q.valid_from = body.valid_from
    if body.valid_until is not None:
        q.valid_until = body.valid_until
    if body.note is not None:
        q.note = body.note
    if q.valid_from > q.valid_until:
        raise HTTPException(status_code=400, detail="有效起日不可晚於迄日")

    write_audit(
        db, "case_institution_quotas", q.id, "UPDATE", user.id,
        before,
        {
            "total_count": q.total_count,
            "valid_from": str(q.valid_from),
            "valid_until": str(q.valid_until),
            "note": q.note,
        },
    )
    db.commit()
    db.refresh(q)
    return _to_response(q, db)


@router.delete("/quotas/{quota_id}", status_code=204)
def delete_quota(
    quota_id: int,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quota 不存在")
    if q.used_count > 0:
        raise HTTPException(status_code=400, detail="已使用過的 Quota 無法刪除")
    write_audit(
        db, "case_institution_quotas", q.id, "DELETE", user.id,
        {"case_id": q.case_id, "institution_id": q.institution_id, "total_count": q.total_count},
        None,
    )
    db.delete(q)
    db.commit()
    return None
