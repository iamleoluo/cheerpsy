"""預約上的「金流資訊」：付款方式、機構額度。

只負責額度的挑選與流轉，不碰流水帳冊、核銷、對帳、月結（那些已移除）。
額度三態的搬動交給 quota_flow（不修改它）；這裡包一層「不擋預約」的處理：
額度不足、已過期、沒有額度時，預約照常建立，只回傳 warnings 讓前端提示。
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution_plan import InstitutionPlan, PlanRateItem, PlanTransportFee
from app.services import quota_flow
from app.services.plan_pricing import pick_rate_item


def _locked(db: Session, quota_id: int) -> CaseInstitutionQuota | None:
    return (
        db.query(CaseInstitutionQuota)
        .filter(CaseInstitutionQuota.id == quota_id)
        .with_for_update(of=CaseInstitutionQuota)
        .first()
    )


def _in_validity(q: CaseInstitutionQuota, on: date) -> bool:
    return (q.valid_from is None or q.valid_from <= on) and (q.valid_until is None or q.valid_until >= on)


def resolve_quota(
    db: Session,
    case_id: int,
    funding_source: str,
    quota_id: int | None,
    appt_date: date,
) -> tuple[CaseInstitutionQuota | None, list[str]]:
    """挑出這場預約要佔用的額度。回傳 (額度或 None, warnings)。

    永遠不因額度問題拒絕預約：沒有可用額度時回 (None, ["…提示…"])，預約照建、不佔額度。
    只有「資料本身不合理」（付款方式不認得、指定的額度不存在或不屬於此個案）才回 4xx。
    """
    warnings: list[str] = []
    if funding_source == "self_pay":
        return None, warnings
    if funding_source != "institution":
        raise HTTPException(status_code=400, detail=f"未支援的付款方式：{funding_source}")

    if quota_id is not None:
        q = _locked(db, quota_id)
        if q is None:
            raise HTTPException(status_code=404, detail="額度不存在")
        if q.case_id != case_id:
            raise HTTPException(status_code=400, detail="額度不屬於此個案")
        if not _in_validity(q, appt_date):
            warnings.append(f"預約日 {appt_date} 不在額度有效期間內")
        if q.reserved_count < 1:
            warnings.append(
                f"機構額度不足（總 {q.total_count} 堂、已用 {q.used_count}、剩餘 {q.reserved_count}），此場預約不佔額度"
            )
            return None, warnings
        return q, warnings

    # 自動挑：有效期內、還有剩餘者，依到期日先到先用
    rows = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            or_(CaseInstitutionQuota.valid_from.is_(None), CaseInstitutionQuota.valid_from <= appt_date),
            or_(CaseInstitutionQuota.valid_until.is_(None), CaseInstitutionQuota.valid_until >= appt_date),
            CaseInstitutionQuota.reserved_count > 0,
            CaseInstitutionQuota.status == "active",
        )
        .order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.asc())
        .all()
    )
    if rows:
        return _locked(db, rows[0].id), warnings
    has_any = db.query(CaseInstitutionQuota.id).filter(CaseInstitutionQuota.case_id == case_id).first()
    warnings.append(
        f"該個案於 {appt_date} 沒有可用的機構額度（額度已用完或已過期），此場預約不佔額度"
        if has_any else "該個案尚未設定機構額度，此場預約不佔額度"
    )
    return None, warnings


def hold_quota(q: CaseInstitutionQuota | None) -> None:
    """排預約：已預留 → 已預約。resolve_quota 已確認有剩餘，這裡不會丟例外。"""
    if q is not None:
        quota_flow.reserve_to_booked(q)


def _flow_quietly(db: Session, quota_id: int | None, step) -> None:
    """取消／未到／報到時的額度流轉。狀態異常（例如歷史資料）只略過，不擋住報到或取消。"""
    if not quota_id:
        return
    q = _locked(db, quota_id)
    if q is None:
        return
    try:
        step(q)
    except HTTPException:
        pass


def release_quota(db: Session, quota_id: int | None) -> None:
    """取消／未到：已預約 → 退回已預留。"""
    _flow_quietly(db, quota_id, quota_flow.booked_to_reserved)


def consume_quota(db: Session, quota_id: int | None) -> None:
    """報到「已到」：已預約 → 已使用。"""
    _flow_quietly(db, quota_id, quota_flow.booked_to_used)


def quota_summary(db: Session, quota_id: int | None) -> dict | None:
    """日曆與預約列表顯示用：總堂數、已用、剩餘、是否最後一次、機構名稱。"""
    if not quota_id:
        return None
    q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
    if q is None:
        return None
    return {
        "institution_name": q.institution.name if q.institution else None,
        "used": q.used_count,
        "total": q.total_count,
        "remaining": q.reserved_count,
        "is_last": (q.reserved_count + q.booked_count) == 1,
    }


# ---------------------------------------------------------------------------
# 定價：預約建立／改方案時，由方案價目算出「應收」與「個案自付額」，存成快照
# ---------------------------------------------------------------------------
@dataclass
class Pricing:
    funding: str
    amount: Decimal
    self_pay: Decimal
    transport_fee: Decimal = Decimal("0")
    plan_id: int | None = None
    rate_item_id: int | None = None
    transport_option_id: int | None = None
    manual_adjusted: bool = False  # 機構案：行政手動改了應收（要寫稽核）
    computed_amount: Decimal | None = None  # 手動調整前，方案算出的應收
    warnings: list[str] = field(default_factory=list)


def _D(v) -> Decimal:
    return Decimal(str(v))


def _plan_or_400(db: Session, plan_id: int) -> InstitutionPlan:
    plan = db.query(InstitutionPlan).filter(InstitutionPlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=400, detail="方案不存在")
    return plan


def _session_seq(db: Session, case_id: int | None, plan_id: int, exclude_id: int | None = None) -> int:
    """該個案在此方案下的第幾次（階梯計價）：已排定與已執行的預約數 + 1（不再依賴已移除的流水帳冊）。"""
    if not case_id:
        return 1
    q = db.query(Appointment.id).filter(
        Appointment.case_id == case_id,
        Appointment.plan_id == plan_id,
        Appointment.status.in_(("booked", "executed")),
    )
    if exclude_id is not None:
        q = q.filter(Appointment.id != exclude_id)
    return q.count() + 1


def compute_pricing(
    db: Session,
    *,
    case_id: int | None,
    funding: str,
    quota: CaseInstitutionQuota | None,
    plan_id: int | None,
    rate_item_id: int | None,
    transport_option_id: int | None,
    session_type: str,
    duration_minutes: int | None,
    manual_amount: float | Decimal | None,
    exclude_appointment_id: int | None = None,
) -> Pricing:
    """算出應收與自付額。

    自費：金額必填（個案要付的全額），自付額＝全額，沒有方案。
    機構：方案價目帶出應收與自付額；行政可手動調整應收（自付額不超過應收）。
    價目挑選：指定的 rate_item_id → 否則依方案、時長、第幾次自動挑 → 都沒有就退回合約鐘點費。
    交通費：指定的選項 → 否則外出用預設選項、現場為 0。
    """
    if funding == "self_pay":
        if manual_amount is None:
            raise HTTPException(status_code=422, detail="自費預約請填金額")
        amt = _D(manual_amount)
        return Pricing(funding="self_pay", amount=amt, self_pay=amt)

    warnings: list[str] = []
    plan = _plan_or_400(db, plan_id) if plan_id else (quota.plan if quota is not None and quota.plan_id else None)
    if plan is None:
        warnings.append("尚未指定機構方案，無法帶出應收與自付額，請手動填金額")
        amt = _D(manual_amount) if manual_amount is not None else Decimal("0")
        return Pricing(funding="institution", amount=amt, self_pay=Decimal("0"), warnings=warnings,
                       manual_adjusted=manual_amount is not None, computed_amount=Decimal("0"))

    item: PlanRateItem | None = None
    if rate_item_id is not None:
        item = next((r for r in plan.rate_items if r.id == rate_item_id and not r.is_no_show_fee), None)
        if item is None:
            raise HTTPException(status_code=400, detail="價目項目不屬於這個方案")
    else:
        item = pick_rate_item(
            db, plan, duration_minutes=duration_minutes,
            session_seq=_session_seq(db, case_id, plan.id, exclude_appointment_id),
        )
    if item is not None:
        total, self_pay = _D(item.total_amount), min(_D(item.self_pay_amount or 0), _D(item.total_amount))
    elif plan.contract is not None:
        total = _D(plan.contract.hourly_rate)
        self_pay = min(_D(plan.contract.self_pay_amount or 0), total)
        warnings.append("方案沒有價目表，改用合約鐘點費與自付額")
    else:
        total, self_pay = Decimal("0"), Decimal("0")
        warnings.append("方案沒有價目，請手動填金額")

    transport = Decimal("0")
    option: PlanTransportFee | None = None
    if transport_option_id is not None:
        option = next((t for t in plan.transport_fees if t.id == transport_option_id), None)
        if option is None:
            raise HTTPException(status_code=400, detail="交通費選項不屬於這個方案")
    elif session_type == "outdoor":
        option = next((t for t in plan.transport_fees if t.is_default), None)
    if option is not None:
        transport = _D(option.amount)

    computed = total
    manual = manual_amount is not None and _D(manual_amount) != total
    if manual_amount is not None:
        total = _D(manual_amount)
        self_pay = min(self_pay, total)
    return Pricing(
        funding="institution", amount=total, self_pay=self_pay, transport_fee=transport,
        plan_id=plan.id, rate_item_id=item.id if item else None,
        transport_option_id=option.id if option else None,
        manual_adjusted=manual, computed_amount=computed, warnings=warnings,
    )


def apply_pricing(a: Appointment, p: Pricing) -> None:
    a.funding_source = p.funding
    a.amount = p.amount
    a.self_pay_amount = p.self_pay
    a.plan_id = p.plan_id
    a.rate_item_id = p.rate_item_id
    a.transport_fee = p.transport_fee
    a.transport_fee_option_id = p.transport_option_id


def billing_options(db: Session, case) -> dict:
    """預約表單用：這個個案可選的方案、價目項目、交通費選項（只含該個案額度所屬方案與其機構的有效方案）。"""
    from sqlalchemy import or_ as _or

    quotas = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.case_id == case.id).all()
    plan_ids = {q.plan_id for q in quotas if q.plan_id}
    query = db.query(InstitutionPlan).filter(InstitutionPlan.status == "active")
    if case.institution_id:
        from app.models.institution_contract import InstitutionContract

        inst_plans = (
            db.query(InstitutionPlan.id)
            .join(InstitutionContract, InstitutionContract.id == InstitutionPlan.contract_id)
            .filter(InstitutionContract.institution_id == case.institution_id)
        )
        query = query.filter(_or(InstitutionPlan.id.in_(plan_ids or {0}), InstitutionPlan.id.in_(inst_plans)))
    else:
        query = query.filter(InstitutionPlan.id.in_(plan_ids or {0}))
    plans = query.order_by(InstitutionPlan.name).all()
    quota_plan = {q.plan_id: q.id for q in quotas if q.plan_id}
    return {
        "funding_source": case.funding_source,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "quota_id": quota_plan.get(p.id),
                "rate_items": [
                    {
                        "id": r.id, "label": r.label, "total_amount": float(r.total_amount),
                        "self_pay_amount": float(r.self_pay_amount or 0),
                        "duration_minutes": r.duration_minutes, "service_type": r.service_type,
                        "session_seq_from": r.session_seq_from, "session_seq_to": r.session_seq_to,
                    }
                    for r in p.rate_items if not r.is_no_show_fee
                ],
                "transport_fees": [
                    {"id": t.id, "label": t.label, "amount": float(t.amount), "is_default": t.is_default}
                    for t in p.transport_fees
                ],
            }
            for p in plans
        ],
    }
