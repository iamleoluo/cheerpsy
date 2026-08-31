"""Real-time settlement: appointments whose end time has passed -> executed + session_records.

Lazy materialization: called on ledger reads. Any booked appointment whose end
time (upper bound of time_range) is <= now is converted into a SessionRecord.
Commission rate and funding source are snapshotted at materialization time
(i.e. the bill-generation moment), reading the *current* User/Case values.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution_plan import InstitutionPlan
from app.models.session_record import SessionRecord
from app.services import quota_flow
from app.models.user import User

DEFAULT_COMMISSION_RATE = Decimal("0.70")

SETTLEMENT_LEAD_MINUTES = 20


def _calc_outdoor_bonus(amount: Decimal, rate: Decimal) -> tuple[Decimal, str | None]:
    """外出（outdoor）保底計算。

    公式：bonus = max(0, min(amount, MIN) - amount * rate)
    語意：心理師抽成補至 OUTPATIENT_MIN_FEE，但診所不墊錢 —
    當 amount 本身低於 MIN 時，最多只能全額讓利給心理師、診所領 0。
    回傳：(bonus, note) — bonus=0 時 note=None。
    """
    min_fee = Decimal(str(settings.OUTPATIENT_MIN_FEE))
    base = amount * rate
    target = min(amount, min_fee)
    bonus = target - base
    if bonus <= 0:
        return Decimal("0"), None
    bonus = bonus.quantize(Decimal("0.01"))
    if amount < min_fee:
        note = f"系統自動補足心理師抽成至全額 ${int(amount)}（總額不足 ${int(min_fee)}，診所讓利）"
    else:
        note = f"系統自動補足心理師抽成至 ${int(min_fee)}"
    return bonus, note


def next_receipt_no(db: Session, d: date) -> str:
    """Clinic-wide receipt number: R{YYYYMMDD}{seq:04d} (seq per session_date)."""
    count = (
        db.query(SessionRecord)
        .filter(SessionRecord.session_date == d)
        .count()
    )
    return f"R{d.strftime('%Y%m%d')}{count + 1:04d}"


def materialize_due_appointments(db: Session, up_to: datetime | None = None) -> dict:
    """Convert all booked appointments whose end time has passed into session records."""
    if up_to is None:
        up_to = datetime.now(timezone.utc)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.status == "booked",
            text("upper(time_range) - (:lead || ' minutes')::interval <= :u")
            .bindparams(lead=str(SETTLEMENT_LEAD_MINUTES), u=up_to),
        )
        .all()
    )

    therapist_cache: dict[int, User] = {}
    case_cache: dict[int, Case] = {}
    materialized = 0
    skipped = 0

    for appt in appointments:
        existing = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
        if existing:
            skipped += 1
            continue

        if appt.therapist_id not in therapist_cache:
            therapist_cache[appt.therapist_id] = (
                db.query(User).filter(User.id == appt.therapist_id).first()
            )
        therapist = therapist_cache[appt.therapist_id]

        if appt.case_id not in case_cache:
            case_cache[appt.case_id] = (
                db.query(Case).filter(Case.id == appt.case_id).first()
            )
        case = case_cache[appt.case_id]

        rate = DEFAULT_COMMISSION_RATE
        if therapist and therapist.commission_rate is not None:
            rate = Decimal(str(therapist.commission_rate))

        # funding source priority: appointment field > case fallback > self_pay
        funding = appt.funding_source or (case.funding_source if case else "self_pay")
        session_date = appt.time_range.lower.date()

        # 額度扣減改走 quota_flow（Phase 3）：已預約 → 已使用。
        # 舊寫法直接 used_count+1，會與報到端點重複扣、也會打破三態恆等式
        # （used+booked+reserved=total，由 DB CHECK 強制）。
        # checkin_status='arrived' 代表已由櫃檯報到並扣過額度，此處不可再扣。
        if funding == "institution" and appt.quota_id and appt.checkin_status != "arrived":
            q = db.query(CaseInstitutionQuota).filter(
                CaseInstitutionQuota.id == appt.quota_id
            ).with_for_update().first()
            if not q or q.booked_count < 1:
                # 額度異常，跳過留待人工檢視
                skipped += 1
                continue
            quota_flow.booked_to_used(q)

        # 拆帳：機構案自付額由方案帶出，其餘為機構請款額
        total = Decimal(str(appt.amount))
        if funding == "institution":
            plan_self_pay = Decimal("0")
            if appt.plan_id:
                plan = db.query(InstitutionPlan).filter(InstitutionPlan.id == appt.plan_id).first()
                if plan and plan.contract:
                    plan_self_pay = Decimal(str(plan.contract.self_pay_amount))
            self_pay = min(plan_self_pay, total)
            inst_claim = total - self_pay
            track = "institution"
        else:
            self_pay, inst_claim = total, Decimal("0")
            track = "monthly" if (case and case.billing_cycle == "monthly") else "immediate"

        appt.status = "executed"
        if appt.checkin_status == "pending":
            # 視訊／外展不到櫃檯報到，超過時段自動視為已到
            appt.checkin_status = "arrived"
        record = SessionRecord(
            appointment_id=appt.id,
            session_date=session_date,
            case_id=appt.case_id,
            therapist_id=appt.therapist_id,
            session_type=appt.session_type,
            room_id=appt.room_id,
            fee_category="counseling",
            amount=appt.amount,
            commission_rate_used=rate,
            funding_source=funding,
            payment_status="unpaid",
            # Phase 1b：金額拆為自付額／機構請款額
            self_pay_amount=self_pay,
            institution_claim_amount=inst_claim,
            # Phase 1b：追款方式決定它進應收帳冊哪一個分頁
            payment_track=track,
            fee_item=appt.fee_item,
        )
        # 外出諮商保底：心理師抽成不足 OUTPATIENT_MIN_FEE 時自動補足（診所不墊錢）
        if appt.session_type == "outdoor":
            bonus, note = _calc_outdoor_bonus(Decimal(str(appt.amount)), rate)
            if bonus > 0:
                record.outcall_bonus = bonus
                record.outcall_note = note
        db.add(record)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            skipped += 1
            continue
        materialized += 1

    db.commit()
    return {"materialized": materialized, "skipped": skipped}


def run_daily_settlement(db: Session, target_date: date | None = None) -> dict:
    """Backward-compatible wrapper for POST /ledger/settle.

    Settles everything up to the end of target_date (or now if not given).
    """
    if target_date is None:
        up_to = datetime.now(timezone.utc)
        label = str(date.today())
    else:
        up_to = datetime(
            target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
        ) + timedelta(days=1)
        label = str(target_date)
    result = materialize_due_appointments(db, up_to)
    return {
        "date": label,
        "executed": result["materialized"],
        "skipped": result["skipped"],
    }

def materialize_appointment(db: Session, appt) -> "SessionRecord | None":
    """把單一已報到的預約寫成帳冊紀錄（櫃檯報到當下呼叫）。

    額度已由呼叫端的 quota_flow.booked_to_used 扣過，此處不再扣。
    已有紀錄則直接回傳，不重複建立。
    """
    existing = (
        db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
    )
    if existing:
        return existing

    case = db.query(Case).filter(Case.id == appt.case_id).first()
    therapist = db.query(User).filter(User.id == appt.therapist_id).first()
    rate = Decimal("0")
    if therapist and therapist.commission_rate is not None:
        rate = Decimal(str(therapist.commission_rate))
    funding = appt.funding_source or (case.funding_source if case else "self_pay")
    session_date = appt.time_range.lower.date()

    total = Decimal(str(appt.amount))
    if funding == "institution":
        plan_self_pay = Decimal("0")
        if appt.plan_id:
            plan = db.query(InstitutionPlan).filter(InstitutionPlan.id == appt.plan_id).first()
            if plan and plan.contract:
                plan_self_pay = Decimal(str(plan.contract.self_pay_amount))
        self_pay = min(plan_self_pay, total)
        inst_claim = total - self_pay
        track = "institution"
    else:
        self_pay, inst_claim = total, Decimal("0")
        track = "monthly" if (case and case.billing_cycle == "monthly") else "immediate"

    record = SessionRecord(
        appointment_id=appt.id,
        session_date=session_date,
        case_id=appt.case_id,
        therapist_id=appt.therapist_id,
        session_type=appt.session_type,
        room_id=appt.room_id,
        fee_category="counseling",
        amount=appt.amount,
        self_pay_amount=self_pay,
        institution_claim_amount=inst_claim,
        payment_track=track,
        fee_item=appt.fee_item,
        commission_rate_used=rate,
        funding_source=funding,
        payment_status="unpaid",
    )
    if appt.session_type == "outdoor":
        bonus, note = _calc_outdoor_bonus(total, rate)
        if bonus > 0:
            record.outcall_bonus = bonus
            record.outcall_note = note
    db.add(record)
    db.flush()
    return record
