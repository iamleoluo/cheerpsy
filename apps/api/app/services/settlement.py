"""Real-time settlement: appointments whose end time has passed -> executed + session_records.

Lazy materialization: called on ledger reads. Any booked appointment whose end
time (upper bound of time_range) is <= now is converted into a SessionRecord.
Commission rate and funding source are snapshotted at materialization time
(i.e. the bill-generation moment), reading the *current* User/Case values.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.funding.registry import get_provider as get_funding_provider
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.session_record import SessionRecord
from app.models.user import User
from app.utils.tz import day_range_utc, today_local, to_local_date

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


def resolve_commission_rate(therapist: User | None) -> Decimal:
    if therapist and therapist.commission_rate is not None:
        return Decimal(str(therapist.commission_rate))
    return DEFAULT_COMMISSION_RATE


def build_session_record(db: Session, appt: Appointment, case: Case | None, therapist: User | None) -> SessionRecord:
    """把一筆 appointment 轉成尚未 add() 的 SessionRecord 本體。

    抽出成獨立函式（P1，出席驅動）是因為現在有<b>兩個呼叫端</b>會走到「appt →
    session_record」這段：① 下面的 materialize_due_appointments()（時間到的
    補登路徑）② routers/appointments.py 的 check-in 端點（使用者按「已到」
    的主要路徑）。兩邊必須產生一模一樣的紀錄，用同一支函式避免兩份邏輯
    日後各自改壞、悄悄長出差異（例如漏了外出保底或漏了報價快照）。

    呼叫端負責：先確認這筆 appt 還沒有 session_record、負責額度扣減
    （consume() 或舊 quota_id 的原子 UPDATE）、負責把 appt.status 設對、
    負責 db.add()/db.flush()/commit()。這支函式只管建構本體，不碰額度、
    不改 appt 的任何欄位。
    """
    rate = resolve_commission_rate(therapist)
    funding = appt.funding_source or (case.funding_source if case else "self_pay")
    session_date = to_local_date(appt.time_range.lower)
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
        receipt_no=next_receipt_no(db, session_date),
        payment_status="unpaid",
        # 機構合約子系統快照：從 appointment 複製過來（07 §4.2）——這張表
        # 才是真正進日報表/月報表/核銷的事實列，快照跟著它走，不跟著
        # appointment 走（appointment 之後可能被改/取消）。
        plan_id=appt.plan_id,
        case_payable=appt.case_payable,
        institution_payable=appt.institution_payable,
        compensation_mode=appt.compensation_mode,
        commissionable_base=appt.commissionable_base,
        plan_quote=appt.plan_quote,
    )
    # 外出諮商保底：心理師抽成不足 OUTPATIENT_MIN_FEE 時自動補足（診所不墊錢）
    if appt.session_type == "outdoor":
        bonus, note = _calc_outdoor_bonus(Decimal(str(appt.amount)), rate)
        if bonus > 0:
            record.outcall_bonus = bonus
            record.outcall_note = note
    return record


def materialize_due_appointments(db: Session, up_to: datetime | None = None) -> dict:
    """把「時間已過但沒人手動報到」的預約自動結算掉。

    P1（出席驅動）之後，這支函式的角色從「預設結算路徑」降級為<b>補登
    安全網</b>——正常流程是使用者在 appointments/{id}/check-in 按「已到」
    （見 routers/appointments.py），那裡會立刻建立 session_record、立刻
    appt.status='executed'。這支函式只處理「行政忘了按」的漏網之魚：
    <code>check_in_status='pending'</code> 且時間已經過去很久（+20 分鐘寬限）的預約。

    <b>Filter 加了 check_in_status == 'pending' 是關鍵修正</b>：如果沒有這一條，
    被人工標記「未到」（check_in_status='no_show'，appt.status 仍是
    'booked'——按設計未到不轉 cancelled，見 01 §C3）的預約，時間一過就會
    被這支函式誤判成「沒人管、自動結算」，產生一筆不該存在的 session_record。
    """
    if up_to is None:
        up_to = datetime.now(timezone.utc)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.status == "booked",
            Appointment.check_in_status == "pending",
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

        funding = appt.funding_source or (case.funding_source if case else "self_pay")

        # Atomic quota deduction if institution-funded with quota（舊 quota_id 路徑）
        if funding == "institution" and appt.quota_id:
            updated = db.execute(
                text(
                    "UPDATE case_institution_quotas SET used_count = used_count + 1 "
                    "WHERE id = :qid AND used_count < total_count"
                ),
                {"qid": appt.quota_id},
            ).rowcount
            if updated == 0:
                # Quota exhausted or missing; skip materialization for human review
                skipped += 1
                continue

        if appt.plan_id:
            try:
                get_funding_provider().consume(db, appt.id)
            except ValueError:
                # 08 決策 §8.3：個案尚未完成初診（無正式病歷號）不能真正消耗額度。
                # 這種情況目前多半代表媒合/初診流程還沒接上（P5 未做），
                # 先跳過此筆留給人工處理，不讓整批結算因為一筆卡住而中斷。
                skipped += 1
                continue

        appt.status = "executed"
        appt.check_in_status = "arrived"
        appt.checked_in_at = up_to
        record = build_session_record(db, appt, case, therapist)
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
        label = str(today_local())
    else:
        # P0 修正：原本用 UTC 午夜切「當天結束」，台北時間會落在早上 08:00——
        # 剛好是營業時段第一格，日結範圍會漏掉/多算凌晨到早上八點這段。
        # 改用 day_range_utc() 算出台北時間 target_date 當天對應的 UTC 區間上界。
        _, up_to = day_range_utc(target_date)
        label = str(target_date)
    result = materialize_due_appointments(db, up_to)
    return {
        "date": label,
        "executed": result["materialized"],
        "skipped": result["skipped"],
    }
