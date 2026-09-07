"""機構合約子系統的管理頁 API：合約／方案／費率規則／個案機構狀態／核銷案容器。

這支路由檔本身是「子系統自己的 API」，掛在 /institution 前綴下，主系統的
其他 router 不會 import 這裡的任何東西（依賴方向規則見 07 §3.2）——會被
其他 router 用到的能力，一律經由 app.funding.registry.get_provider()。

WRITE_ROLES 沿用主系統慣例（見 case_quotas.py、quota_templates.py）。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.funding.dto import QuoteRequest
from app.funding.registry import get_provider
from app.institution.claims import service as claims_service
from app.institution.models.claim_case import InstClaimCase
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.models.institution import Institution
from app.models.user import User

router = APIRouter(prefix="/institution", tags=["institution-subsystem"])

WRITE_ROLES = ["admin", "staff"]


# ─────────────────────────────────────────────────────────────────────────
# 合約
# ─────────────────────────────────────────────────────────────────────────

class ContractCreate(BaseModel):
    institution_id: int
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    eligibility_note: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None


class ContractResponse(BaseModel):
    id: int
    institution_id: int
    institution_name: str | None = None
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    eligibility_note: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    is_active: bool

    model_config = {"from_attributes": True}


def _contract_to_response(c: InstContract) -> ContractResponse:
    return ContractResponse(
        id=c.id,
        institution_id=c.institution_id,
        institution_name=c.institution.name if c.institution else None,
        name=c.name,
        contact_name=c.contact_name,
        contact_phone=c.contact_phone,
        eligibility_note=c.eligibility_note,
        valid_from=c.valid_from,
        valid_until=c.valid_until,
        is_active=c.is_active,
    )


@router.get("/contracts", response_model=list[ContractResponse])
def list_contracts(
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InstContract)
    if not include_inactive:
        q = q.filter(InstContract.is_active.is_(True))
    return [_contract_to_response(c) for c in q.order_by(InstContract.name).all()]


@router.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
def create_contract(
    body: ContractCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    inst = db.query(Institution).filter(Institution.id == body.institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="機構單位不存在，請先在 /institutions 建立")
    c = InstContract(**body.model_dump(), created_by=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _contract_to_response(c)


# ─────────────────────────────────────────────────────────────────────────
# 方案（含費率規則的 nested 讀寫）
# ─────────────────────────────────────────────────────────────────────────

class RateRuleIn(BaseModel):
    sort_order: int = 0
    when: dict = {}
    price_source: str = "fixed"
    unit_price: Decimal | None = None
    case_payable: Decimal = Decimal("0")
    label: str | None = None


class RateRuleOut(RateRuleIn):
    id: int


class PlanCreate(BaseModel):
    contract_id: int
    name: str
    quota_unit: str = "count"
    default_quota_limit: str | None = None  # 原始描述，如 "6+3" / "需評估"
    default_quota_limit_numeric: int | None = None
    period_limit: int | None = None
    period_unit: str | None = None
    requires_assessment: bool = False
    counts_toward_quota: bool = True
    requires_external_code: bool = False
    compensation_mode: str = "commission"
    case_receipt_required: bool = True
    case_receipt_item_name: str | None = None
    institution_receipt_required: bool = False
    institution_receipt_item_name: str | None = None
    claim_group_key: str | None = None
    claim_timing: str = "monthly"
    claim_deadline_day: int | None = None
    claim_grouping_mode: str = "period"
    claim_capacity: int | None = None
    registered_hours_rule: str | None = None
    admin_checklist: list[str] = []
    therapist_checklist: list[str] = []
    notes: str | None = None
    rate_rules: list[RateRuleIn] = []


class PlanResponse(BaseModel):
    id: int
    contract_id: int
    contract_name: str | None = None
    institution_name: str | None = None
    name: str
    quota_unit: str
    default_quota_limit: str | None = None
    default_quota_limit_numeric: int | None = None
    requires_assessment: bool
    counts_toward_quota: bool
    requires_external_code: bool
    compensation_mode: str
    claim_group_key: str | None = None
    claim_timing: str
    claim_grouping_mode: str
    claim_capacity: int | None = None
    is_active: bool
    rate_rules: list[RateRuleOut] = []

    model_config = {"from_attributes": True}


def _plan_to_response(p: InstPlan) -> PlanResponse:
    return PlanResponse(
        id=p.id,
        contract_id=p.contract_id,
        contract_name=p.contract.name if p.contract else None,
        institution_name=p.contract.institution.name if p.contract and p.contract.institution else None,
        name=p.name,
        quota_unit=p.quota_unit,
        default_quota_limit=p.default_quota_limit,
        default_quota_limit_numeric=p.default_quota_limit_numeric,
        requires_assessment=p.requires_assessment,
        counts_toward_quota=p.counts_toward_quota,
        requires_external_code=p.requires_external_code,
        compensation_mode=p.compensation_mode,
        claim_group_key=p.claim_group_key,
        claim_timing=p.claim_timing,
        claim_grouping_mode=p.claim_grouping_mode,
        claim_capacity=p.claim_capacity,
        is_active=p.is_active,
        rate_rules=[
            RateRuleOut(
                id=r.id,
                sort_order=r.sort_order,
                when=json.loads(r.when_json or "{}"),
                price_source=r.price_source,
                unit_price=r.unit_price,
                case_payable=r.case_payable or Decimal("0"),
                label=r.label,
            )
            for r in sorted(p.rate_rules, key=lambda x: x.sort_order)
        ],
    )


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(
    contract_id: int | None = None,
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InstPlan)
    if contract_id:
        q = q.filter(InstPlan.contract_id == contract_id)
    if not include_inactive:
        q = q.filter(InstPlan.is_active.is_(True))
    return [_plan_to_response(p) for p in q.order_by(InstPlan.name).all()]


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: PlanCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = db.query(InstContract).filter(InstContract.id == body.contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="合約不存在")
    data = body.model_dump(exclude={"rate_rules", "admin_checklist", "therapist_checklist"})
    plan = InstPlan(
        **data,
        admin_checklist=json.dumps(body.admin_checklist, ensure_ascii=False),
        therapist_checklist=json.dumps(body.therapist_checklist, ensure_ascii=False),
        created_by=user.id,
    )
    db.add(plan)
    db.flush()
    for rr in body.rate_rules:
        db.add(
            InstRateRule(
                plan_id=plan.id,
                sort_order=rr.sort_order,
                when_json=json.dumps(rr.when, ensure_ascii=False),
                price_source=rr.price_source,
                unit_price=rr.unit_price,
                case_payable=rr.case_payable,
                label=rr.label,
            )
        )
    db.commit()
    db.refresh(plan)
    return _plan_to_response(plan)


# ─────────────────────────────────────────────────────────────────────────
# 報價預覽（不落地，純測試/預覽用；正式建立預約走 POST /appointments 時
# 在同一交易內呼叫 get_provider().quote() + .reserve()，見 07 §5.2 一致性要求）
# ─────────────────────────────────────────────────────────────────────────

class QuotePreviewRequest(BaseModel):
    case_id: int
    plan_id: int
    therapist_id: int
    session_type: str = "in_person"
    visit_seq: int | None = None
    duration_min: int = 60
    location_kind: str = "clinic"
    appt_date: date | None = None


@router.post("/quote-preview")
def quote_preview(
    body: QuotePreviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provider = get_provider()
    req = QuoteRequest(**body.model_dump())
    try:
        quote = provider.quote(db, req)
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return quote


@router.get("/eligible-plans")
def eligible_plans(
    case_id: int,
    on_date: date = Query(default_factory=date.today),
    session_type: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_provider().list_eligible_plans(db, case_id, on_date, session_type)


# ─────────────────────────────────────────────────────────────────────────
# 個案機構狀態（Layer 1）
# ─────────────────────────────────────────────────────────────────────────

class EnrollRequest(BaseModel):
    case_id: int
    plan_id: int
    external_case_code: str | None = None
    quota_limit: int | None = None
    valid_from: date | None = None
    valid_until: date | None = None


@router.get("/cases/{case_id}/enrollments")
def get_case_enrollments(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_provider().get_case_enrollments(db, case_id)


@router.post("/enrollments", status_code=status.HTTP_201_CREATED)
def enroll_case(
    body: EnrollRequest,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    provider = get_provider()
    try:
        result = provider.enroll(
            db,
            case_id=body.case_id,
            plan_id=body.plan_id,
            external_case_code=body.external_case_code,
            quota_limit=body.quota_limit,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
            created_by=user.id,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return result


# ─────────────────────────────────────────────────────────────────────────
# 核銷案容器（Layer 3）—— 見 app/institution/claims/service.py 的完成度說明
# ─────────────────────────────────────────────────────────────────────────

class OpenClaimCaseRequest(BaseModel):
    claim_group_key: str
    grouping_mode: str = "period"
    capacity: int | None = None
    period_start: date | None = None
    period_end: date | None = None


class AttachRecordsRequest(BaseModel):
    session_record_ids: list[int]


class RecordPaymentRequest(BaseModel):
    received_date: date
    received_amount: Decimal
    income_tax_amount: Decimal = Decimal("0")
    transfer_fee: Decimal = Decimal("0")


@router.get("/claim-groups/{claim_group_key}/uncollected")
def list_uncollected(
    claim_group_key: str,
    period_start: date | None = None,
    period_end: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """漏單提醒／跨月遺留提醒共用的查詢。見 07 §4.3。"""
    rows = claims_service.list_uncollected(db, claim_group_key, period_start, period_end)
    return [{"id": r.id, "session_date": r.session_date, "case_id": r.case_id, "amount": r.institution_payable or r.amount} for r in rows]


@router.post("/claim-cases", status_code=status.HTTP_201_CREATED)
def open_claim_case(
    body: OpenClaimCaseRequest,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    cc = claims_service.open_claim_case(db, **body.model_dump(), created_by=user.id)
    db.commit()
    return {"id": cc.id, "claim_no": cc.claim_no, "status": cc.status}


@router.post("/claim-cases/{claim_case_id}/records")
def attach_records(
    claim_case_id: int,
    body: AttachRecordsRequest,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    lines = claims_service.attach_records(db, claim_case_id, body.session_record_ids)
    db.commit()
    return {"attached": len(lines)}


@router.put("/claim-cases/{claim_case_id}/submit")
def submit_claim_case(
    claim_case_id: int,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        cc = claims_service.submit(db, claim_case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.commit()
    return {"id": cc.id, "status": cc.status, "applied_amount": cc.applied_amount}


@router.put("/claim-cases/{claim_case_id}/payment")
def record_claim_payment(
    claim_case_id: int,
    body: RecordPaymentRequest,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    try:
        cc = claims_service.record_payment(db, claim_case_id, **body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.commit()
    return {"id": cc.id, "status": cc.status, "net_received": cc.net_received}


@router.get("/claim-cases")
def list_claim_cases(
    claim_group_key: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InstClaimCase)
    if claim_group_key:
        q = q.filter(InstClaimCase.claim_group_key == claim_group_key)
    if status_filter:
        q = q.filter(InstClaimCase.status == status_filter)
    rows = q.order_by(InstClaimCase.claim_no.desc()).all()
    return [
        {
            "id": c.id,
            "claim_no": c.claim_no,
            "claim_group_key": c.claim_group_key,
            "status": c.status,
            "record_count": len(c.lines),
            "applied_amount": c.applied_amount,
            "net_received": c.net_received,
        }
        for c in rows
    ]
