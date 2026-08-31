from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.institution import Institution
from app.models.institution_contract import InstitutionContract
from app.models.institution_plan import InstitutionPlan
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/institution-contracts", tags=["institution-contracts"])

CAP_TYPES = {"amount", "count", "unlimited"}
STAFF = ["admin", "accountant", "staff"]


class ContractBase(BaseModel):
    name: str
    eligibility: str | None = None
    hourly_rate: float
    self_pay_amount: float = 0
    cap_type: str = "unlimited"
    cap_value: float | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    settlement_direction: str = "to_clinic"
    rebate_rate: float | None = None
    rebate_method: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.cap_type not in CAP_TYPES:
            raise ValueError(f"cap_type must be one of {sorted(CAP_TYPES)}")
        if self.cap_type == "unlimited" and self.cap_value is not None:
            raise ValueError("cap_value must be empty when cap_type is 'unlimited'")
        if self.cap_type != "unlimited" and self.cap_value is None:
            raise ValueError("cap_value is required unless cap_type is 'unlimited'")
        if self.self_pay_amount > self.hourly_rate:
            raise ValueError("個案自付額不可高於方案鐘點費")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("有效起日不可晚於迄日")
        if self.settlement_direction not in ("to_clinic", "to_therapist"):
            raise ValueError("settlement_direction 需為 to_clinic 或 to_therapist")
        if self.settlement_direction == "to_therapist":
            if self.rebate_rate is None:
                raise ValueError("回扣型方案需填寫回繳比例")
            if not (0 <= self.rebate_rate <= 1):
                raise ValueError("回繳比例需介於 0 與 1 之間")
            if self.rebate_method not in ("transfer", "payout_deduct"):
                raise ValueError("回繳方式需為 transfer 或 payout_deduct")
        return self


class ContractCreate(ContractBase):
    institution_id: int


class ContractUpdate(ContractBase):
    pass


class ContractResponse(BaseModel):
    id: int
    institution_id: int
    institution_name: str | None = None
    name: str
    eligibility: str | None = None
    hourly_rate: float
    self_pay_amount: float
    # 機構請款額＝鐘點費 − 自付額，前端不必自己算
    institution_claim_amount: float
    cap_type: str
    cap_value: float | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    is_active: bool
    plan_count: int = 0
    settlement_direction: str = "to_clinic"
    rebate_rate: float | None = None
    rebate_method: str | None = None

    model_config = {"from_attributes": True}


def _to_response(c: InstitutionContract, plan_count: int = 0) -> ContractResponse:
    return ContractResponse(
        id=c.id,
        institution_id=c.institution_id,
        institution_name=c.institution.name if c.institution else None,
        name=c.name,
        eligibility=c.eligibility,
        hourly_rate=float(c.hourly_rate),
        self_pay_amount=float(c.self_pay_amount),
        institution_claim_amount=float(c.hourly_rate) - float(c.self_pay_amount),
        cap_type=c.cap_type,
        cap_value=float(c.cap_value) if c.cap_value is not None else None,
        contact_person=c.contact_person,
        contact_phone=c.contact_phone,
        valid_from=c.valid_from,
        valid_until=c.valid_until,
        is_active=c.is_active,
        plan_count=plan_count,
        settlement_direction=c.settlement_direction,
        rebate_rate=float(c.rebate_rate) if c.rebate_rate is not None else None,
        rebate_method=c.rebate_method,
    )


@router.get("", response_model=list[ContractResponse])
def list_contracts(
    institution_id: int | None = Query(None),
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InstitutionContract)
    if institution_id is not None:
        q = q.filter(InstitutionContract.institution_id == institution_id)
    if not include_inactive:
        q = q.filter(InstitutionContract.is_active.is_(True))
    contracts = q.order_by(InstitutionContract.id.desc()).all()

    counts = dict(
        db.query(InstitutionPlan.contract_id, func.count(InstitutionPlan.id))
        .group_by(InstitutionPlan.contract_id)
        .all()
    )
    return [_to_response(c, counts.get(c.id, 0)) for c in contracts]


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
def create_contract(
    body: ContractCreate,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    inst = db.query(Institution).filter(Institution.id == body.institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")

    c = InstitutionContract(
        institution_id=body.institution_id,
        name=body.name.strip(),
        eligibility=body.eligibility,
        hourly_rate=body.hourly_rate,
        self_pay_amount=body.self_pay_amount,
        cap_type=body.cap_type,
        cap_value=body.cap_value,
        contact_person=body.contact_person,
        contact_phone=body.contact_phone,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        settlement_direction=body.settlement_direction,
        rebate_rate=body.rebate_rate,
        rebate_method=body.rebate_method,
        created_by=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    write_audit(db, "institution_contracts", c.id, "INSERT", user.id, None, {"name": c.name})
    db.commit()
    return _to_response(c)


@router.put("/{contract_id}", response_model=ContractResponse)
def update_contract(
    contract_id: int,
    body: ContractUpdate,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    c = db.query(InstitutionContract).filter(InstitutionContract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    before = {
        "name": c.name,
        "hourly_rate": float(c.hourly_rate),
        "self_pay_amount": float(c.self_pay_amount),
        "cap_type": c.cap_type,
        "cap_value": float(c.cap_value) if c.cap_value is not None else None,
    }
    c.name = body.name.strip()
    c.eligibility = body.eligibility
    c.hourly_rate = body.hourly_rate
    c.self_pay_amount = body.self_pay_amount
    c.cap_type = body.cap_type
    c.cap_value = body.cap_value
    c.contact_person = body.contact_person
    c.contact_phone = body.contact_phone
    c.valid_from = body.valid_from
    c.valid_until = body.valid_until
    c.settlement_direction = body.settlement_direction
    c.rebate_rate = body.rebate_rate
    c.rebate_method = body.rebate_method
    after = {
        "name": c.name,
        "hourly_rate": float(c.hourly_rate),
        "self_pay_amount": float(c.self_pay_amount),
        "cap_type": c.cap_type,
        "cap_value": float(c.cap_value) if c.cap_value is not None else None,
    }
    # 合約調價不回溯：已產生的紀錄鐘點費在建立當下就鎖定
    # （gap_analysis §3.2 contracts ②，與 session_records.commission_rate_used 一致）
    write_audit(db, "institution_contracts", c.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_contract(
    contract_id: int,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    c = db.query(InstitutionContract).filter(InstitutionContract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    c.is_active = False
    write_audit(db, "institution_contracts", c.id, "UPDATE", user.id,
                {"is_active": True}, {"is_active": False})
    db.commit()
