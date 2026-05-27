from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.quota_template import QuotaTemplate
from app.models.user import User
from app.schemas.case_quota import QuotaResponse
from app.schemas.quota_template import (
    QuotaTemplateApply,
    QuotaTemplateCreate,
    QuotaTemplateResponse,
    QuotaTemplateUpdate,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/quota-templates", tags=["quota-templates"])

WRITE_ROLES = ["admin", "staff"]


def _to_response(t: QuotaTemplate) -> QuotaTemplateResponse:
    return QuotaTemplateResponse(
        id=t.id,
        institution_id=t.institution_id,
        institution_name=t.institution.name if t.institution else None,
        name=t.name,
        total_count=t.total_count,
        notes=t.notes,
        default_valid_from=t.default_valid_from,
        default_valid_until=t.default_valid_until,
        created_by=t.created_by,
        created_at=t.created_at,
    )


@router.get("/", response_model=list[QuotaTemplateResponse])
def list_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(QuotaTemplate).order_by(QuotaTemplate.institution_id, QuotaTemplate.name).all()
    return [_to_response(t) for t in rows]


@router.post("/", response_model=QuotaTemplateResponse)
def create_template(
    body: QuotaTemplateCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    if body.default_valid_from and body.default_valid_until and body.default_valid_from > body.default_valid_until:
        raise HTTPException(status_code=400, detail="預設有效起日不可晚於迄日")
    t = QuotaTemplate(
        institution_id=body.institution_id,
        name=body.name,
        total_count=body.total_count,
        notes=body.notes,
        default_valid_from=body.default_valid_from,
        default_valid_until=body.default_valid_until,
        created_by=user.id,
    )
    db.add(t)
    db.flush()
    write_audit(db, "quota_templates", t.id, "create", user.id, None, {"name": t.name})
    db.commit()
    db.refresh(t)
    return _to_response(t)


@router.put("/{template_id}", response_model=QuotaTemplateResponse)
def update_template(
    template_id: int,
    body: QuotaTemplateUpdate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    t = db.query(QuotaTemplate).filter(QuotaTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="範本不存在")
    before = {
        "name": t.name,
        "total_count": t.total_count,
        "default_valid_from": str(t.default_valid_from) if t.default_valid_from else None,
        "default_valid_until": str(t.default_valid_until) if t.default_valid_until else None,
    }
    if body.name is not None:
        t.name = body.name
    if body.total_count is not None:
        t.total_count = body.total_count
    if body.notes is not None:
        t.notes = body.notes
    if body.clear_default_valid_from:
        t.default_valid_from = None
    elif body.default_valid_from is not None:
        t.default_valid_from = body.default_valid_from
    if body.clear_default_valid_until:
        t.default_valid_until = None
    elif body.default_valid_until is not None:
        t.default_valid_until = body.default_valid_until
    if t.default_valid_from and t.default_valid_until and t.default_valid_from > t.default_valid_until:
        raise HTTPException(status_code=400, detail="預設有效起日不可晚於迄日")
    write_audit(
        db, "quota_templates", t.id, "update", user.id, before,
        {
            "name": t.name,
            "total_count": t.total_count,
            "default_valid_from": str(t.default_valid_from) if t.default_valid_from else None,
            "default_valid_until": str(t.default_valid_until) if t.default_valid_until else None,
        },
    )
    db.commit()
    db.refresh(t)
    return _to_response(t)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    t = db.query(QuotaTemplate).filter(QuotaTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="範本不存在")
    write_audit(db, "quota_templates", t.id, "delete", user.id, {"name": t.name}, None)
    db.delete(t)
    db.commit()


@router.post("/{template_id}/apply", response_model=list[QuotaResponse])
def apply_template(
    template_id: int,
    body: QuotaTemplateApply,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """批次套用範本：為每個 case_id 建立一筆 CaseInstitutionQuota。"""
    t = db.query(QuotaTemplate).filter(QuotaTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="範本不存在")

    if not body.case_ids:
        raise HTTPException(status_code=400, detail="請選擇至少一個個案")

    # 套用日期：呼叫端傳入優先；否則 fallback 到範本預設值；皆無則 NULL（永久）
    valid_from = body.valid_from if body.valid_from is not None else t.default_valid_from
    valid_until = body.valid_until if body.valid_until is not None else t.default_valid_until
    if valid_from and valid_until and valid_from > valid_until:
        raise HTTPException(status_code=400, detail="有效起日不可晚於迄日")

    cases = db.query(Case).filter(Case.id.in_(body.case_ids)).all()
    found_ids = {c.id for c in cases}
    missing = set(body.case_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"個案不存在：{list(missing)}")

    created: list[CaseInstitutionQuota] = []
    for case_id in body.case_ids:
        q = CaseInstitutionQuota(
            case_id=case_id,
            institution_id=t.institution_id,
            total_count=t.total_count,
            used_count=0,
            valid_from=valid_from,
            valid_until=valid_until,
            note=f"套用範本：{t.name}",
            created_by=user.id,
        )
        db.add(q)
        db.flush()
        write_audit(db, "case_institution_quotas", q.id, "create", user.id, None, {"template_id": template_id, "case_id": case_id})
        created.append(q)

    db.commit()
    for q in created:
        db.refresh(q)

    from app.routers.case_quotas import _to_response as quota_to_response
    return [quota_to_response(q, db) for q in created]
