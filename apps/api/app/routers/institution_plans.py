from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution_contract import InstitutionContract
from app.models.institution_plan import InstitutionPlan, PlanTransportFee
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/institution-plans", tags=["institution-plans"])

PLAN_STATUS = {"active", "exhausted", "expired"}
STAFF = ["admin", "accountant", "staff"]


class TransportFeeIn(BaseModel):
    label: str
    amount: float = 0
    is_default: bool = False


class TransportFeeOut(TransportFeeIn):
    id: int

    model_config = {"from_attributes": True}


class PlanBase(BaseModel):
    name: str
    claim_unit: str | None = None
    claim_contact: str | None = None
    claim_phone: str | None = None
    # None 代表「不限」
    per_person_count: int | None = None
    annual_total_count: int | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    transport_fees: list[TransportFeeIn] = []

    @model_validator(mode="after")
    def _check(self):
        if self.per_person_count is not None and self.per_person_count <= 0:
            raise ValueError("每人次數需大於 0，不限請留空")
        if self.annual_total_count is not None and self.annual_total_count <= 0:
            raise ValueError("年度總次數需大於 0，不限請留空")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("有效起日不可晚於迄日")
        if sum(1 for t in self.transport_fees if t.is_default) > 1:
            raise ValueError("交通費選項只能有一個預設值")
        return self


class PlanCreate(PlanBase):
    contract_id: int


class PlanUpdate(PlanBase):
    pass


class PlanResponse(BaseModel):
    id: int
    contract_id: int
    contract_name: str | None = None
    institution_id: int | None = None
    institution_name: str | None = None
    name: str
    claim_unit: str | None = None
    claim_contact: str | None = None
    claim_phone: str | None = None
    per_person_count: int | None = None
    annual_total_count: int | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    status: str
    # 由合約帶下來，前端排預約時要用
    hourly_rate: float | None = None
    self_pay_amount: float | None = None
    transport_fees: list[TransportFeeOut] = []
    # 年度總量使用情形（跨個案彙總）
    annual_used: int = 0
    annual_booked: int = 0
    annual_reserved: int = 0
    case_count: int = 0

    model_config = {"from_attributes": True}


class QuotaTriState(BaseModel):
    """方案子列表：一列一個個案的額度三態。"""

    quota_id: int
    case_id: int
    case_name: str
    total_count: int
    used_count: int
    booked_count: int
    reserved_count: int
    valid_from: date | None = None
    valid_until: date | None = None
    status: str
    note: str | None = None
    is_last_session: bool = False


def _agg(db: Session, plan_ids: list[int]) -> dict[int, dict]:
    if not plan_ids:
        return {}
    rows = (
        db.query(
            CaseInstitutionQuota.plan_id,
            func.coalesce(func.sum(CaseInstitutionQuota.used_count), 0),
            func.coalesce(func.sum(CaseInstitutionQuota.booked_count), 0),
            func.coalesce(func.sum(CaseInstitutionQuota.reserved_count), 0),
            func.count(CaseInstitutionQuota.id),
        )
        .filter(CaseInstitutionQuota.plan_id.in_(plan_ids))
        .group_by(CaseInstitutionQuota.plan_id)
        .all()
    )
    return {
        r[0]: {"used": int(r[1]), "booked": int(r[2]), "reserved": int(r[3]), "cases": int(r[4])}
        for r in rows
    }


def _to_response(p: InstitutionPlan, agg: dict | None = None) -> PlanResponse:
    a = agg or {}
    contract = p.contract
    return PlanResponse(
        id=p.id,
        contract_id=p.contract_id,
        contract_name=contract.name if contract else None,
        institution_id=contract.institution_id if contract else None,
        institution_name=contract.institution.name if contract and contract.institution else None,
        name=p.name,
        claim_unit=p.claim_unit,
        claim_contact=p.claim_contact,
        claim_phone=p.claim_phone,
        per_person_count=p.per_person_count,
        annual_total_count=p.annual_total_count,
        valid_from=p.valid_from,
        valid_until=p.valid_until,
        notes=p.notes,
        status=p.status,
        hourly_rate=float(contract.hourly_rate) if contract else None,
        self_pay_amount=float(contract.self_pay_amount) if contract else None,
        transport_fees=[TransportFeeOut.model_validate(t) for t in p.transport_fees],
        annual_used=a.get("used", 0),
        annual_booked=a.get("booked", 0),
        annual_reserved=a.get("reserved", 0),
        case_count=a.get("cases", 0),
    )


def _sync_transport_fees(db: Session, plan: InstitutionPlan, fees: list[TransportFeeIn]) -> None:
    for existing in list(plan.transport_fees):
        db.delete(existing)
    db.flush()
    for f in fees:
        db.add(
            PlanTransportFee(
                plan_id=plan.id, label=f.label.strip(), amount=f.amount, is_default=f.is_default
            )
        )


@router.get("", response_model=list[PlanResponse])
def list_plans(
    contract_id: int | None = Query(None),
    institution_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InstitutionPlan).join(InstitutionContract)
    if contract_id is not None:
        q = q.filter(InstitutionPlan.contract_id == contract_id)
    if institution_id is not None:
        q = q.filter(InstitutionContract.institution_id == institution_id)
    if status_filter:
        q = q.filter(InstitutionPlan.status == status_filter)
    plans = q.order_by(InstitutionPlan.id.desc()).all()
    agg = _agg(db, [p.id for p in plans])
    return [_to_response(p, agg.get(p.id)) for p in plans]


@router.get("/{plan_id}/quotas", response_model=list[QuotaTriState])
def list_plan_quotas(
    plan_id: int,
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """方案子列表（個案清冊）：每個個案的額度三態。"""
    plan = db.query(InstitutionPlan).filter(InstitutionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Not found")

    q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.plan_id == plan_id)
    if not include_archived:
        q = q.filter(CaseInstitutionQuota.status.in_(["active", "exhausted"]))

    out: list[QuotaTriState] = []
    for r in q.all():
        remaining = r.reserved_count + r.booked_count
        out.append(
            QuotaTriState(
                quota_id=r.id,
                case_id=r.case_id,
                case_name=r.case.name if r.case else "",
                total_count=r.total_count,
                used_count=r.used_count,
                booked_count=r.booked_count,
                reserved_count=r.reserved_count,
                valid_from=r.valid_from,
                valid_until=r.valid_until,
                status=r.status,
                note=r.note,
                # 只剩最後一次 → 前端整列標黃、日曆方塊加紅框
                is_last_session=(remaining == 1),
            )
        )
    return out


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: PlanCreate,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    contract = db.query(InstitutionContract).filter(InstitutionContract.id == body.contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    p = InstitutionPlan(
        contract_id=body.contract_id,
        name=body.name.strip(),
        claim_unit=body.claim_unit,
        claim_contact=body.claim_contact,
        claim_phone=body.claim_phone,
        per_person_count=body.per_person_count,
        annual_total_count=body.annual_total_count,
        valid_from=body.valid_from or contract.valid_from,
        valid_until=body.valid_until or contract.valid_until,
        notes=body.notes,
        created_by=user.id,
    )
    db.add(p)
    db.flush()
    _sync_transport_fees(db, p, body.transport_fees)
    db.commit()
    db.refresh(p)
    write_audit(db, "institution_plans", p.id, "INSERT", user.id, None, {"name": p.name})
    db.commit()
    return _to_response(p)


@router.put("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: int,
    body: PlanUpdate,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    p = db.query(InstitutionPlan).filter(InstitutionPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")

    before = {"name": p.name, "per_person_count": p.per_person_count,
              "annual_total_count": p.annual_total_count, "status": p.status}
    p.name = body.name.strip()
    p.claim_unit = body.claim_unit
    p.claim_contact = body.claim_contact
    p.claim_phone = body.claim_phone
    p.per_person_count = body.per_person_count
    p.annual_total_count = body.annual_total_count
    p.valid_from = body.valid_from
    p.valid_until = body.valid_until
    p.notes = body.notes
    _sync_transport_fees(db, p, body.transport_fees)
    after = {"name": p.name, "per_person_count": p.per_person_count,
             "annual_total_count": p.annual_total_count, "status": p.status}
    write_audit(db, "institution_plans", p.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(p)
    agg = _agg(db, [p.id])
    return _to_response(p, agg.get(p.id))


@router.put("/{plan_id}/status", response_model=PlanResponse)
def set_plan_status(
    plan_id: int,
    new_status: str = Query(..., alias="value"),
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    if new_status not in PLAN_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(PLAN_STATUS)}")
    p = db.query(InstitutionPlan).filter(InstitutionPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    before = {"status": p.status}
    p.status = new_status
    write_audit(db, "institution_plans", p.id, "UPDATE", user.id, before, {"status": p.status})
    db.commit()
    db.refresh(p)
    agg = _agg(db, [p.id])
    return _to_response(p, agg.get(p.id))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    p = db.query(InstitutionPlan).filter(InstitutionPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    in_use = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.plan_id == plan_id).count()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"已有 {in_use} 位個案掛在此方案，請改為將狀態設為「已過期」",
        )
    write_audit(db, "institution_plans", p.id, "DELETE", user.id, {"name": p.name}, None)
    db.delete(p)
    db.commit()
