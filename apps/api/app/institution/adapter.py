"""機構合約子系統對外的唯一實作面——把 app.funding.ports.FundingPlanProvider
的 8 支方法兜起來。這支檔案可以自由 import 主系統的 model（Case、Appointment、
SessionRecord），因為依賴方向允許「子 → 主」（見 07 §3.2）。

主系統只透過 app.funding.registry.get_provider() 拿到這個類別的實例，
從不 import 這支檔案本身。main.py 啟動時註冊一次即可。

目前完成度（誠實標記，「架構先起來」階段）：
    ✅ list_eligible_plans / quote / get_case_enrollments / enroll
    ✅ reserve / consume / release / close_case_enrollments 的額度三態轉移
    ⚠️ 尚未實作，模型欄位已留、邏輯留 TODO：
       - quota_pool 方案層級總量檢查（國軍 $149,000 那種池）
       - period_limit 週期性子上限（容愛協會每月4次）
       - extended_count 額度延長的申請/核准流程
       - requires_external_code 在 consume 時「待補代號」的標記與核銷收納擋下
       這些都在 07 文件描述的規則範圍內，先把主流程跑通，複雜規則逐一補上。
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.funding.dto import (
    ChecklistPlan,
    ClaimRouting,
    CompensationPlan,
    EnrollmentState,
    PlanOption,
    PricingResult,
    Quote,
    QuotaBeforeState,
    QuotaEffect,
    QuoteRequest,
    ReceiptPlan,
    ReceiptSpec,
)
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.institution.rules.pricing import RateRuleContext, resolve_rate
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.user import User

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def _load_checklist(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


class InstitutionFundingProvider:
    """機構合約子系統。實作 app.funding.ports.FundingPlanProvider。"""

    # ------------------------------------------------------------------
    # 查詢類
    # ------------------------------------------------------------------

    def list_eligible_plans(
        self, db: Session, case_id: int, on_date: date, session_type: str | None = None
    ) -> list[PlanOption]:
        enrollments = (
            db.query(InstEnrollment)
            .filter(
                InstEnrollment.case_id == case_id,
                InstEnrollment.status.in_(["active", "exhausted"]),
                or_(InstEnrollment.valid_from.is_(None), InstEnrollment.valid_from <= on_date),
                or_(InstEnrollment.valid_until.is_(None), InstEnrollment.valid_until >= on_date),
            )
            .all()
        )
        options: list[PlanOption] = []
        for e in enrollments:
            plan: InstPlan = e.plan
            if plan is None or not plan.is_active:
                continue
            booked = (
                db.query(func.count(Appointment.id))
                .filter(Appointment.plan_id == plan.id, Appointment.case_id == case_id, Appointment.status == "booked")
                .scalar()
                or 0
            )
            limit = e.quota_limit
            used = float(e.used_count or 0)
            reserved = float(e.reserved_count or 0)
            extended = float(e.extended_count or 0)
            # 恆等式 used + reserved + booked = limit + extended 永遠成立（三態互相
            # 移轉、不會離開這個池），所以拿這個和 total 比較是恆真式，測不出「額度
            # 是否用罄」。真正的訊號是「還有沒有已預留可以被拿去用」：reserved<=0
            # 代表沒有空位可以再建立新預約；reserved==1 代表這次要建立的話會是
            # 最後一次。（此處由端到端煙霧測試抓到並修正，2026/09/07）
            is_full = limit is not None and reserved <= 0
            is_last = limit is not None and reserved == 1
            summary = None
            if limit is not None:
                summary = f"{plan.name} {int(used + booked)}/{int(float(limit) + extended)}"
            options.append(
                PlanOption(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    institution_name=plan.contract.institution.name if plan.contract and plan.contract.institution else None,
                    quota_summary=summary,
                    is_last=is_last,
                    disabled=is_full,
                    disabled_reason="額度已用罄" if is_full else None,
                )
            )
        return options

    def quote(self, db: Session, request: QuoteRequest) -> Quote:
        plan = db.query(InstPlan).filter(InstPlan.id == request.plan_id).first()
        if plan is None:
            raise ValueError(f"方案不存在：plan_id={request.plan_id}")

        rules = (
            db.query(InstRateRule)
            .filter(InstRateRule.plan_id == plan.id)
            .order_by(InstRateRule.sort_order.asc())
            .all()
        )
        rule_dicts = [
            {
                "id": r.id,
                "when_json": r.when_json,
                "price_source": r.price_source,
                "unit_price": r.unit_price,
                "case_payable": r.case_payable,
                "label": r.label,
            }
            for r in rules
        ]
        ctx = RateRuleContext(
            session_type=request.session_type,
            visit_seq=request.visit_seq,
            duration_min=request.duration_min,
            location_kind=request.location_kind,
            sub_unit=request.sub_unit,
        )
        matched = resolve_rate(rule_dicts, ctx)
        resolved_by: list[str] = []
        if matched and matched.price_source == "therapist_rate":
            therapist = db.query(User).filter(User.id == request.therapist_id).first()
            base = therapist.base_price if therapist and therapist.base_price is not None else Decimal("0")
            unit_price = Decimal(str(base))
            case_payable = Decimal("0")
            resolved_by.append(f"{matched.resolved_by} -> therapist_rate({unit_price})")
        elif matched:
            unit_price = matched.unit_price or Decimal("0")
            case_payable = matched.case_payable
            resolved_by.append(matched.resolved_by)
        else:
            # 沒有規則命中（方案還沒建規則）——保守回傳 0，不讓報價流程整個炸掉，
            # 但這是明確的資料缺漏，畫面應該要能看出金額是 0 並提示行政補規則。
            unit_price = Decimal("0")
            case_payable = Decimal("0")
            resolved_by.append("no_rule_matched (fallback 0 — 請補建此方案的費率規則)")

        institution_payable = unit_price - case_payable
        if institution_payable < 0:
            institution_payable = Decimal("0")

        # 額度效果
        enrollment = (
            db.query(InstEnrollment)
            .filter(InstEnrollment.case_id == request.case_id, InstEnrollment.plan_id == plan.id)
            .first()
        )
        quota_effect = self._build_quota_effect(db, plan, enrollment)

        # 薪酬
        commissionable_base = unit_price  # TODO: 扣除 commissionable=False 的 addon 後才是真正基準
        comp = CompensationPlan(mode=plan.compensation_mode, commissionable_base=commissionable_base)

        receipts = ReceiptPlan(
            case=ReceiptSpec(required=plan.case_receipt_required, item_name=plan.case_receipt_item_name),
            institution=ReceiptSpec(
                required=plan.institution_receipt_required, item_name=plan.institution_receipt_item_name
            ),
        )
        claim = ClaimRouting(
            group_key=plan.claim_group_key or plan.name,
            timing=plan.claim_timing,
            deadline_day=plan.claim_deadline_day,
            grouping_mode=plan.claim_grouping_mode,
            capacity=plan.claim_capacity,
            registered_hours_rule={"note": plan.registered_hours_rule} if plan.registered_hours_rule else None,
        )
        checklists = ChecklistPlan(
            admin=_load_checklist(plan.admin_checklist), therapist=_load_checklist(plan.therapist_checklist)
        )

        return Quote(
            quote_id=f"q_{uuid.uuid4().hex[:10]}",
            plan_id=plan.id,
            plan_name=plan.name,
            contract_id=plan.contract_id,
            institution_name=plan.contract.institution.name if plan.contract and plan.contract.institution else None,
            pricing=PricingResult(
                unit_price=unit_price, case_payable=case_payable, institution_payable=institution_payable, addons=[]
            ),
            receipts=receipts,
            quota=quota_effect,
            compensation=comp,
            claim=claim,
            checklists=checklists,
            resolved_by=resolved_by,
        )

    def _build_quota_effect(self, db: Session, plan: InstPlan, enrollment: InstEnrollment | None) -> QuotaEffect:
        if not plan.counts_toward_quota or enrollment is None:
            return QuotaEffect(consumes=False)
        if enrollment.assessment_status == "pending":
            return QuotaEffect(
                consumes=False,
                enrollment_id=enrollment.id,
                blocking="此方案需先經評估通過才能預約（assessment_status=pending）",
            )
        booked = (
            db.query(func.count(Appointment.id))
            .filter(Appointment.plan_id == plan.id, Appointment.case_id == enrollment.case_id, Appointment.status == "booked")
            .scalar()
            or 0
        )
        limit = enrollment.quota_limit
        used = float(enrollment.used_count or 0)
        reserved = float(enrollment.reserved_count or 0)
        extended = float(enrollment.extended_count or 0)
        before = QuotaBeforeState(
            used=int(used), booked=int(booked), reserved=int(reserved), limit=int(float(limit)) if limit is not None else None
        )
        blocking = None
        is_last = False
        if limit is not None:
            # 見 list_eligible_plans 同一處註解：用 reserved 本身判斷，不要拿
            # used+reserved+booked 跟 total 比較（那個和恆等於 total，測不出東西）。
            if reserved <= 0:
                blocking = "額度已用罄（已預留為 0，沒有空位可再建立新預約）"
            elif reserved == 1:
                is_last = True
        return QuotaEffect(
            consumes=True, enrollment_id=enrollment.id, before=before, is_last=is_last, blocking=blocking
        )

    def get_case_enrollments(self, db: Session, case_id: int) -> list[EnrollmentState]:
        rows = db.query(InstEnrollment).filter(InstEnrollment.case_id == case_id).all()
        out = []
        for e in rows:
            plan = e.plan
            out.append(
                EnrollmentState(
                    enrollment_id=e.id,
                    plan_id=e.plan_id,
                    plan_name=plan.name if plan else "",
                    institution_name=plan.contract.institution.name if plan and plan.contract and plan.contract.institution else None,
                    external_case_code=e.external_case_code,
                    quota_unit=e.quota_unit,
                    quota_limit=e.quota_limit,
                    used=e.used_count,
                    booked=Decimal(
                        str(
                            db.query(func.count(Appointment.id))
                            .filter(Appointment.plan_id == e.plan_id, Appointment.case_id == case_id, Appointment.status == "booked")
                            .scalar()
                            or 0
                        )
                    ),
                    reserved=e.reserved_count,
                    extended_count=int(e.extended_count or 0),
                    valid_from=e.valid_from,
                    valid_until=e.valid_until,
                    assessment_status=e.assessment_status,
                    status=e.status,
                )
            )
        return out

    # ------------------------------------------------------------------
    # 命令類
    # ------------------------------------------------------------------

    def enroll(
        self, db: Session, case_id: int, plan_id: int, external_case_code: str | None = None, **kwargs
    ) -> EnrollmentState:
        existing = (
            db.query(InstEnrollment).filter(InstEnrollment.case_id == case_id, InstEnrollment.plan_id == plan_id).first()
        )
        if existing:
            raise ValueError("此個案已加入過此方案（同一人不可重複加入同一方案）")
        plan = db.query(InstPlan).filter(InstPlan.id == plan_id).first()
        if plan is None:
            raise ValueError(f"方案不存在：plan_id={plan_id}")

        limit = kwargs.get("quota_limit", plan.default_quota_limit_numeric)
        e = InstEnrollment(
            case_id=case_id,
            plan_id=plan_id,
            external_case_code=external_case_code,
            quota_unit=plan.quota_unit,
            quota_limit=limit,
            reserved_count=limit if limit is not None else 0,  # 全數先預留（08 決策 §8.3、07 §4.1）
            used_count=0,
            period_limit=plan.period_limit,
            period_unit=plan.period_unit,
            valid_from=kwargs.get("valid_from"),
            valid_until=kwargs.get("valid_until"),
            assessment_status="pending" if plan.requires_assessment else "not_required",
            status="active",
            created_by=kwargs.get("created_by"),
        )
        db.add(e)
        db.flush()
        return EnrollmentState(
            enrollment_id=e.id,
            plan_id=plan_id,
            plan_name=plan.name,
            external_case_code=external_case_code,
            quota_unit=e.quota_unit,
            quota_limit=e.quota_limit,
            used=Decimal("0"),
            booked=Decimal("0"),
            reserved=e.reserved_count,
            valid_from=e.valid_from,
            valid_until=e.valid_until,
            assessment_status=e.assessment_status,
            status=e.status,
        )

    def _get_enrollment_for_appointment(self, db: Session, appt: Appointment) -> InstEnrollment | None:
        if appt.plan_id is None:
            return None
        return (
            db.query(InstEnrollment)
            .filter(InstEnrollment.case_id == appt.case_id, InstEnrollment.plan_id == appt.plan_id)
            .first()
        )

    def reserve(self, db: Session, appointment_id: int, quote: Quote) -> None:
        if not quote.quota.consumes or quote.quota.enrollment_id is None:
            return
        e = db.query(InstEnrollment).filter(InstEnrollment.id == quote.quota.enrollment_id).first()
        if e is None:
            return
        # 已預留 -1（已預約本身不落地，由 status='booked' 的 appointment 數量代表）
        e.reserved_count = (e.reserved_count or 0) - 1
        if e.reserved_count < 0:
            e.reserved_count = 0  # 防禦：不讓資料因競態或重複呼叫變負數
        # flush（非 commit）：呼叫端仍在同一交易內，但緊接著的 db.refresh()／
        # 下一步查詢要能看到這個變更。純靠 Session autoflush 在直接呼叫
        # adapter（非經過會先 commit 的 router）的情境下不夠可靠，回歸測試
        # 抓到過（2026/09/07）。
        db.flush()

    def consume(self, db: Session, appointment_id: int) -> None:
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if appt is None:
            return
        e = self._get_enrollment_for_appointment(db, appt)
        if e is None:
            return
        # 08 決策 §8.3 前置檢查：必須已有正式病歷號才能真正消耗額度（產生金流）。
        case = db.query(Case).filter(Case.id == appt.case_id).first()
        if case is not None and not case.case_number:
            raise ValueError("此個案尚未完成初診（無正式病歷號），不能執行 consume()。請先完成初診報到。")
        e.used_count = (e.used_count or 0) + 1
        # TODO: requires_external_code 為 true 但 e.external_case_code 仍是 NULL 時，
        # 這裡先放行（不卡報到收款），但要在核銷收納（inst_claim_lines 建立）時擋下。
        db.flush()

    def release(self, db: Session, appointment_id: int, reason: str) -> None:
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if appt is None:
            return
        e = self._get_enrollment_for_appointment(db, appt)
        if e is None:
            return
        # 已預約 → 已預留（不是釋回！個案仍保有額度，見 08 決策 C3）
        e.reserved_count = (e.reserved_count or 0) + 1
        db.flush()

    def close_case_enrollments(self, db: Session, case_id: int) -> None:
        rows = db.query(InstEnrollment).filter(InstEnrollment.case_id == case_id).all()
        for e in rows:
            # 已預留＋已預約全數歸零：把上限鎖定在目前已使用量（沿用主系統
            # cases.py 對 case_institution_quotas 的既有寫法）
            e.quota_limit = e.used_count
            e.reserved_count = 0
            e.status = "closed"
        db.flush()
