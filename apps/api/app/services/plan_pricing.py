"""機構方案的計價與核銷門檻。

依《系統架構規劃與機構合約清冊 對照確認事項》實作。

⚠️ 這裡實作的是**資料模型能表達什麼**，不是政策決定。下列仍待慈恩回覆
（見 open_questions.md Q25–Q31），程式中以可設定的方式處理、不預設立場：
  - 未達核銷門檻的紀錄要怎麼處理（扣住？先入案再篩？）→ 目前標記但不阻擋
  - 個案未做滿門檻就中斷，費用怎麼算 → 目前不自動處理，交行政判斷
  - 跨月達標時金額歸哪一個月 → 目前歸「達標當次」所在月
  - 回繳比例與方式 → 由合約設定，未設定則不計算
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution_plan import InstitutionPlan, PlanRateItem
from app.models.session_record import SessionRecord


def pick_rate_item(
    db: Session,
    plan: InstitutionPlan,
    *,
    service_type: str | None = None,
    duration_minutes: int | None = None,
    session_seq: int | None = None,
) -> PlanRateItem | None:
    """依服務型態／時長／第幾次挑出適用的價目。

    比對規則：條件有填的欄位才比對，NULL 視為「不限」。
    多筆符合時取最精確的（有指定條件的優先），再取 sort_order。
    """
    candidates = [r for r in plan.rate_items if not r.is_no_show_fee]

    def matches(r: PlanRateItem) -> bool:
        if r.service_type and service_type and r.service_type != service_type:
            return False
        if r.duration_minutes and duration_minutes and r.duration_minutes != duration_minutes:
            return False
        if session_seq is not None:
            if r.session_seq_from and session_seq < r.session_seq_from:
                return False
            if r.session_seq_to and session_seq > r.session_seq_to:
                return False
        return True

    def specificity(r: PlanRateItem) -> tuple:
        # 條件越具體排越前面
        return (
            -(r.service_type is not None),
            -(r.duration_minutes is not None),
            -(r.session_seq_from is not None or r.session_seq_to is not None),
            r.sort_order,
            r.id,
        )

    hits = sorted([r for r in candidates if matches(r)], key=specificity)
    return hits[0] if hits else None


def no_show_fee_item(plan: InstitutionPlan) -> PlanRateItem | None:
    """該方案是否有約定爽約費（如南家扶 $200）。"""
    for r in plan.rate_items:
        if r.is_no_show_fee:
            return r
    return None


def next_session_seq(db: Session, case_id: int, plan_id: int) -> int:
    """該個案在此方案下的第幾次（用於階梯計價）。"""
    n = (
        db.query(func.count(SessionRecord.id))
        .join(CaseInstitutionQuota, CaseInstitutionQuota.case_id == SessionRecord.case_id)
        .filter(
            SessionRecord.case_id == case_id,
            CaseInstitutionQuota.plan_id == plan_id,
            SessionRecord.is_void.is_(False),
        )
        .scalar()
        or 0
    )
    return n + 1


def split_amount(item: PlanRateItem) -> tuple[Decimal, Decimal]:
    """回傳 (個案自付額, 機構請款額)。"""
    total = Decimal(str(item.total_amount))
    self_pay = Decimal(str(item.self_pay_amount or 0))
    return self_pay, total - self_pay


def claim_registration(item: PlanRateItem, actual_hours: Decimal | float = 1) -> tuple[Decimal, Decimal]:
    """核銷單上要登記的（時數, 單價）。

    多數方案就是實際時數與實際單價；少數方案（台南地院、台南女中、
    輔諮中心南一區）因機構預算科目單價固定，要用時數湊出金額。
    """
    if item.claim_hours is not None and item.claim_unit_rate is not None:
        return Decimal(str(item.claim_hours)), Decimal(str(item.claim_unit_rate))
    hours = Decimal(str(actual_hours))
    _, inst = split_amount(item)
    unit = (inst / hours) if hours else inst
    return hours, unit


def threshold_status(db: Session, plan: InstitutionPlan, case_id: int) -> dict:
    """個案在此方案下是否已達核銷門檻（問題1）。

    9 個方案有此規則：人事處系列 7 局處與社工支持服務達 4 次、脆弱家庭達 8 次。
    未達門檻**不阻擋**加入核銷案，只回傳狀態供 UI 標示 —— 實際作業方式
    （行政手動扣住？系統擋下？）待慈恩回覆。
    """
    threshold = plan.claim_threshold_sessions
    done = (
        db.query(func.count(SessionRecord.id))
        .join(CaseInstitutionQuota, CaseInstitutionQuota.case_id == SessionRecord.case_id)
        .filter(
            SessionRecord.case_id == case_id,
            CaseInstitutionQuota.plan_id == plan.id,
            SessionRecord.is_void.is_(False),
        )
        .scalar()
        or 0
    )
    if not threshold:
        return {"has_threshold": False, "done": done, "threshold": None, "reached": True}
    return {
        "has_threshold": True,
        "done": done,
        "threshold": threshold,
        "reached": done >= threshold,
        "remaining": max(threshold - done, 0),
    }


def monthly_limit_status(db: Session, plan: InstitutionPlan, case_id: int, ref: date) -> dict:
    """每月上限檢查（容愛協會：每月最多 4 次）。"""
    limit = plan.per_person_monthly_limit
    if not limit:
        return {"has_limit": False}
    first = date(ref.year, ref.month, 1)
    last_next = date(ref.year + (ref.month == 12), (ref.month % 12) + 1, 1)
    used = (
        db.query(func.count(SessionRecord.id))
        .join(CaseInstitutionQuota, CaseInstitutionQuota.case_id == SessionRecord.case_id)
        .filter(
            SessionRecord.case_id == case_id,
            CaseInstitutionQuota.plan_id == plan.id,
            SessionRecord.session_date >= first,
            SessionRecord.session_date < last_next,
            SessionRecord.is_void.is_(False),
        )
        .scalar()
        or 0
    )
    return {
        "has_limit": True,
        "limit": limit,
        "used_this_month": used,
        "remaining": max(limit - used, 0),
        "exceeded": used >= limit,
    }


def effective_person_cap(plan: InstitutionPlan, quota: CaseInstitutionQuota) -> int | None:
    """個案的實際可用次數上限＝方案基本次數 ＋ 已核准的延長次數。"""
    if plan.per_person_count is None:
        return None
    return plan.per_person_count + (quota.extension_granted or 0)


def rebate_amount(contract, institution_claim: Decimal | float) -> Decimal | None:
    """回扣型方案：心理師應回繳給慈恩的金額（問題4）。

    回傳 None 代表這不是回扣型、或尚未設定回繳比例。
    """
    if contract.settlement_direction != "to_therapist":
        return None
    if contract.rebate_rate is None:
        return None
    return (Decimal(str(institution_claim)) * Decimal(str(contract.rebate_rate))).quantize(Decimal("0.01"))
