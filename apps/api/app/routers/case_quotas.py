from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution import Institution
from app.models.institution_plan import InstitutionPlan, PlanRateItem
from app.services import appt_billing
from app.models.user import User
from app.schemas.case_quota import QuotaCreate, QuotaResponse, QuotaUpdate
from app.services.audit import write_audit

router = APIRouter(tags=["case-quotas"])

WRITE_ROLES = ["admin", "staff"]


def _to_response(q: CaseInstitutionQuota, db: Session) -> QuotaResponse:
    # 額度三態以 DB 欄位為唯一真相（Phase 3 起由 quota_flow 維護，
    # 並有 CHECK 強制 used+booked+reserved=total）。
    # 這裡不再即時數 appointments —— 那會變成同一件事的第二個來源。
    #
    # 相容說明：response 的 `reserved_count` 欄位語意是「已預約」，
    # 對應 DB 的 booked_count；DB 的 reserved_count（已預留）另以
    # `pool_reserved_count` 回傳。欄位名維持不動以免打斷既有前端。
    return QuotaResponse(
        id=q.id,
        case_id=q.case_id,
        case_name=q.case.name if q.case else None,
        institution_id=q.institution_id,
        institution_name=q.institution.name if q.institution else None,
        plan_id=q.plan_id,
        plan_name=q.plan.name if q.plan else None,
        total_count=q.total_count,
        used_count=q.used_count,
        reserved_count=q.booked_count,
        pool_reserved_count=q.reserved_count,
        remaining=q.reserved_count,
        valid_from=q.valid_from,
        valid_until=q.valid_until,
        note=q.note,
    )


def _require_case_access(db: Session, case_id: int, user: User) -> Case:
    """心理師只能看自己個案的額度；別人的個案一律 404（不洩漏是否存在）。"""
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c or (user.role == "therapist" and c.therapist_id != user.id):
        raise HTTPException(status_code=404, detail="個案不存在")
    return c


@router.get("/cases/{case_id}/quotas", response_model=list[QuotaResponse])
def list_case_quotas(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_case_access(db, case_id, user)
    rows = (
        db.query(CaseInstitutionQuota)
        .filter(CaseInstitutionQuota.case_id == case_id)
        .order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.asc())
        .all()
    )
    return [_to_response(q, db) for q in rows]


@router.get("/cases/{case_id}/billing-options")
def case_billing_options(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """預約表單用：這個個案可選的方案、價目項目、交通費。心理師只看得到自己個案的（別人的回 404）。"""
    case = _require_case_access(db, case_id, user)
    return appt_billing.billing_options(db, case)


@router.get("/cases/{case_id}/pricing-preview")
def pricing_preview(
    case_id: int,
    on_date: date = Query(..., description="預約日"),
    duration_minutes: int | None = Query(None),
    quota_id: int | None = Query(None),
    plan_id: int | None = Query(None),
    rate_item_id: int | None = Query(None),
    transport_fee_option_id: int | None = Query(None),
    consult_type: str | None = Query(None),
    service_type: str | None = Query(None),
    session_type: str = Query("in_person"),
    amount: float | None = Query(None, description="手動調整的總額"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """預約表單即時預覽：用與建立預約相同的計價（價目挑選、第幾次依日期、交通費），不寫入任何資料。"""
    from datetime import datetime as _dt, time as _time, timezone as _tz

    case = _require_case_access(db, case_id, user)
    quota, warnings = appt_billing.resolve_quota(db, case.id, "institution", quota_id, on_date)
    start = _dt.combine(on_date, _time(0, 0), tzinfo=_tz.utc)
    try:
        price = appt_billing.compute_pricing(
            db, case_id=case.id, funding="institution", quota=quota, plan_id=plan_id,
            rate_item_id=rate_item_id, transport_option_id=transport_fee_option_id,
            session_type=session_type, duration_minutes=duration_minutes, manual_amount=amount,
            consult_type=consult_type or ("couple" if case.case_type == "couple" else "individual"),
            service_type=service_type, start_time=start,
        )
    except HTTPException as e:
        return {"error": e.detail, "warnings": warnings}
    item = db.get(PlanRateItem, price.rate_item_id) if price.rate_item_id else None
    plan = db.get(InstitutionPlan, price.plan_id) if price.plan_id else None
    return {
        "error": None,
        "plan_name": plan.name if plan else None,
        "rate_item_label": item.label if item else None,
        "amount": float(price.amount),
        "self_pay_amount": float(price.self_pay) if price.self_pay is not None else None,
        "institution_subsidy": (float(price.amount - price.self_pay) if price.self_pay is not None else None),
        "transport_fee": float(price.transport_fee),
        "warnings": warnings + price.warnings,
    }


@router.get("/cases/{case_id}/quotas/available", response_model=list[QuotaResponse])
def list_available_quotas(
    case_id: int,
    institution_id: int | None = Query(None),
    on_date: date | None = Query(None, description="預約日；預設今日"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """有效 Quota：valid_from ≤ on_date ≤ valid_until 且剩餘 > 0；依 valid_until 升冪（FIFO）。

    NULL 視為無時間上限：valid_from IS NULL → 無起日下限；valid_until IS NULL → 永久有效。
    """
    _require_case_access(db, case_id, user)
    target = on_date or date.today()
    q = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            or_(CaseInstitutionQuota.valid_from.is_(None), CaseInstitutionQuota.valid_from <= target),
            or_(CaseInstitutionQuota.valid_until.is_(None), CaseInstitutionQuota.valid_until >= target),
            CaseInstitutionQuota.used_count < CaseInstitutionQuota.total_count,
        )
    )
    if institution_id is not None:
        q = q.filter(CaseInstitutionQuota.institution_id == institution_id)
    rows = q.order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.asc()).all()
    return [_to_response(r, db) for r in rows]


@router.get("/quotas", response_model=list[QuotaResponse])
def list_all_quotas(
    active_only: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跨個案列表，供「機構額度」分頁使用。"""
    q = db.query(CaseInstitutionQuota)
    if user.role == "therapist":
        q = q.filter(
            CaseInstitutionQuota.case_id.in_(
                db.query(Case.id).filter(Case.therapist_id == user.id)
            )
        )
    if active_only:
        today = date.today()
        q = q.filter(
            or_(CaseInstitutionQuota.valid_from.is_(None), CaseInstitutionQuota.valid_from <= today),
            or_(CaseInstitutionQuota.valid_until.is_(None), CaseInstitutionQuota.valid_until >= today),
            CaseInstitutionQuota.used_count < CaseInstitutionQuota.total_count,
        )
    rows = q.order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.desc()).all()
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
    if body.plan_id is not None:
        plan = db.query(InstitutionPlan).filter(InstitutionPlan.id == body.plan_id).first()
        if not plan or not plan.contract or plan.contract.institution_id != body.institution_id:
            raise HTTPException(status_code=400, detail="方案不存在，或不屬於這個機構")
    if body.total_count <= 0:
        raise HTTPException(status_code=400, detail="總次數需大於 0")
    if body.valid_from and body.valid_until and body.valid_from > body.valid_until:
        raise HTTPException(status_code=400, detail="有效起日不可晚於迄日")

    q = CaseInstitutionQuota(
        case_id=case_id,
        institution_id=body.institution_id,
        plan_id=body.plan_id,
        total_count=body.total_count,
        used_count=0,
        # 加入方案時全數進「已預留」，維持 used+booked+reserved=total 恆等式
        # （gap_analysis §1.4 額度三態）
        booked_count=0,
        reserved_count=body.total_count,
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
            "valid_from": str(body.valid_from) if body.valid_from else None,
            "valid_until": str(body.valid_until) if body.valid_until else None,
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
        "valid_from": str(q.valid_from) if q.valid_from else None,
        "valid_until": str(q.valid_until) if q.valid_until else None,
        "note": q.note,
    }
    if body.total_count is not None:
        if body.total_count < q.used_count:
            raise HTTPException(status_code=400, detail=f"總次數不可少於已用次數 {q.used_count}")
        if body.total_count < q.used_count + q.booked_count:
            raise HTTPException(
                status_code=400,
                detail=f"總次數不可少於已用 {q.used_count} ＋ 已預約 {q.booked_count}",
            )
        # 差額全部反映在「已預留」，維持恆等式
        q.reserved_count = body.total_count - q.used_count - q.booked_count
        q.total_count = body.total_count
    if body.clear_valid_from:
        q.valid_from = None
    elif body.valid_from is not None:
        q.valid_from = body.valid_from
    if body.clear_valid_until:
        q.valid_until = None
    elif body.valid_until is not None:
        q.valid_until = body.valid_until
    if body.note is not None:
        q.note = body.note
    if q.valid_from and q.valid_until and q.valid_from > q.valid_until:
        raise HTTPException(status_code=400, detail="有效起日不可晚於迄日")

    write_audit(
        db, "case_institution_quotas", q.id, "UPDATE", user.id,
        before,
        {
            "total_count": q.total_count,
            "valid_from": str(q.valid_from) if q.valid_from else None,
            "valid_until": str(q.valid_until) if q.valid_until else None,
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
