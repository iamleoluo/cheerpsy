import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from psycopg2.extras import DateTimeTZRange
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.appointment_admin_task import AppointmentAdminTask
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.fee_item import FeeItem
from app.models.receipt import Receipt
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services import numbering, room_occupancy
from app.services.audit import write_audit
from app.services.settlement import SETTLEMENT_LEAD_MINUTES, build_session_record
from app.utils.tz import to_local_date
# 機構合約子系統整合（07 §3.2 依賴反轉）：只能 import funding/，不可 import
# app.institution.* ——這條規則本身由這兩行 import 示範遵守。
from app.funding.dto import QuoteRequest
from app.funding.registry import get_provider as get_funding_provider
from app.schemas.appointment import (
    AppointmentBatchCreate,
    AppointmentCreate,
    AppointmentPaymentUpdate,
    AppointmentResponse,
    AppointmentUpdate,
    CheckInRequest,
    IssueReceiptRequest,
    IssueReceiptResponse,
    PaymentStepRequest,
    PaymentStepResponse,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def _next_appointment_number(db: Session, therapist_code: str, dt: datetime) -> str:
    """預約編號 R-{YYYYMMDD}-{代碼}-{流水3碼}。配號走 services/numbering.py
    的序列表（06 P0），日期取自預約起始時間，所以補歷史預約會拿到當時的日期。

    日期用**台北日期**，跟 session_records.session_date 一致。原本是直接
    dt.date()（UTC 日期），晚上 8 點以後的預約會被編成前一天的號——行政用
    編號找「今天的預約」就會找不到。
    """
    return numbering.next_appointment_number(
        db, on_date=to_local_date(dt), therapist_code=therapist_code
    )


def _next_visit_seq(db: Session, case_id: int) -> int:
    current_max = db.query(func.max(Appointment.visit_seq)).filter(
        Appointment.case_id == case_id
    ).scalar()
    return (current_max or 0) + 1


def _get_commission_rate(therapist: User) -> Decimal:
    if therapist.commission_rate is not None:
        return Decimal(str(therapist.commission_rate))
    return DEFAULT_COMMISSION_RATE


def _to_response(
    a: Appointment,
    therapist: User | None = None,
    db: Session | None = None,
    viewer: User | None = None,
) -> AppointmentResponse:
    start = end = None
    if a.time_range:
        start = a.time_range.lower
        end = a.time_range.upper
    rate = _get_commission_rate(therapist) if therapist else DEFAULT_COMMISSION_RATE
    quota_inst_name = None
    if a.quota_id and db is not None:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
        quota_inst_name = q.institution.name if q and q.institution else None
    # 報到三步驟（收款/開據）的目前狀態，前端靠這個決定顯示哪一步。
    # 見 01 §A2、payment_step()/issue_receipt()。
    copay_collected_at = copay_payment_method = None
    receipt_no = None
    if db is not None and a.check_in_status == "arrived":
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == a.id).first()
        if sr:
            copay_collected_at = sr.copay_collected_at
            copay_payment_method = sr.copay_payment_method
            if sr.copay_collected_at is not None:
                receipt = (
                    db.query(Receipt)
                    .filter(Receipt.session_record_id == sr.id, Receipt.status == "issued")
                    .first()
                )
                receipt_no = receipt.receipt_no if receipt else None
    # 個案名稱隱私：管理員/行政可見；治療師只見自己的；其他角色（會計等）不可見
    can_see_name = viewer is None or viewer.role in ("admin", "staff") or (
        viewer.role == "therapist" and a.therapist_id == viewer.id
    )
    # 合療判定：couple_case_id 有值，或 case 本身就是伴侶案
    is_couple = a.couple_case_id is not None or (a.case is not None and a.case.case_type == "couple")
    couple_name = None
    if is_couple and can_see_name:
        if a.couple_case_id and a.couple_case:
            couple_name = a.couple_case.name
        elif a.case and a.case.case_type == "couple":
            couple_name = a.case.name
    return AppointmentResponse(
        id=a.id,
        appointment_number=a.appointment_number,
        case_id=a.case_id,
        case_name=(a.case.name if a.case else None) if can_see_name else None,
        case_type=(a.case.case_type if a.case else "individual"),
        couple_case_id=a.couple_case_id,
        couple_name=couple_name,
        is_couple=is_couple,
        therapist_id=a.therapist_id,
        therapist_name=a.therapist.name if a.therapist else None,
        room_id=a.room_id,
        room_name=a.room.name if a.room else None,
        session_type=a.session_type,
        consult_type=a.consult_type or "individual",
        location_kind=a.location_kind or "clinic",
        start_time=start,
        end_time=end,
        amount=float(a.amount),
        funding_source=a.funding_source or "self_pay",
        quota_id=a.quota_id,
        quota_institution_name=quota_inst_name,
        therapist_share=round(float(a.amount) * float(rate), 2),
        clinic_share=round(float(a.amount) * (1 - float(rate)), 2),
        visit_seq=a.visit_seq,
        status=a.status,
        batch_id=a.batch_id,
        created_at=a.created_at,
        plan_id=a.plan_id,
        # 讀自己存的快照，不查 inst_plans（依賴方向規則，見上方 import 註解）
        plan_name=(a.plan_quote or {}).get("plan_name") if a.plan_quote else None,
        case_payable=float(a.case_payable) if a.case_payable is not None else None,
        institution_payable=float(a.institution_payable) if a.institution_payable is not None else None,
        compensation_mode=a.compensation_mode,
        check_in_status=a.check_in_status,
        checked_in_at=a.checked_in_at,
        no_show_reason=a.no_show_reason,
        no_show_note=a.no_show_note,
        no_show_followup=a.no_show_followup,
        copay_collected_at=copay_collected_at,
        copay_payment_method=copay_payment_method,
        receipt_no=receipt_no,
    )


def _validate_couple(db: Session, couple_case_id: int | None, payer_case_id: int) -> Case | None:
    """合療驗證：couple_case_id 必為伴侶案，付款方(payer_case_id)必為伴侶案本身或其成員。

    回傳伴侶案 Case（供取得共同心理師），非合療回傳 None。
    """
    if not couple_case_id:
        return None
    couple = db.query(Case).filter(Case.id == couple_case_id).first()
    if not couple or couple.case_type != "couple":
        raise HTTPException(status_code=400, detail="couple_case_id 不是伴侶案")
    member_ids = [link.member_case_id for link in couple.couple_links]
    if payer_case_id not in ([couple.id] + member_ids):
        raise HTTPException(status_code=400, detail="付款方必須是該伴侶案本身或其成員")
    return couple


def _resolve_quota(
    db: Session,
    case_id: int,
    funding_source: str,
    quota_id: int | None,
    appt_date: date,
) -> int | None:
    """Validate and (optionally) auto-pick a quota for this appointment.

    Returns the quota id to attach, or None for self_pay.
    Raises HTTPException for invalid combinations.
    """
    if funding_source == "self_pay":
        return None
    if funding_source != "institution":
        raise HTTPException(status_code=400, detail=f"未支援的付款方式：{funding_source}")

    if quota_id is not None:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Quota 不存在")
        if q.case_id != case_id:
            raise HTTPException(status_code=400, detail="Quota 不屬於此個案")
        # NULL valid_from/valid_until 視為無時間上限（P0 修正：原本直接用 Python 比較，
        # 遇到 NULL 會丟 TypeError → 500；改用與 case_quotas.py 一致的寫法）
        if (q.valid_from and appt_date < q.valid_from) or (q.valid_until and appt_date > q.valid_until):
            raise HTTPException(status_code=400, detail=f"預約日 {appt_date} 不在 Quota 有效期間 {q.valid_from} ~ {q.valid_until}")
        reserved = db.query(Appointment).filter(
            Appointment.quota_id == q.id,
            Appointment.status == "booked",
        ).count()
        if q.used_count + reserved >= q.total_count:
            raise HTTPException(status_code=400, detail="該扣額已用完或被預約鎖定")
        return q.id

    # Auto-pick FIFO by valid_until (also check reserved)
    # NULL valid_from/valid_until 視為無時間上限（見上方註解）
    candidates = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            or_(CaseInstitutionQuota.valid_from.is_(None), CaseInstitutionQuota.valid_from <= appt_date),
            or_(CaseInstitutionQuota.valid_until.is_(None), CaseInstitutionQuota.valid_until >= appt_date),
            CaseInstitutionQuota.used_count < CaseInstitutionQuota.total_count,
        )
        .order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.asc())
        .all()
    )
    candidate = None
    for cq in candidates:
        reserved = db.query(Appointment).filter(
            Appointment.quota_id == cq.id,
            Appointment.status == "booked",
        ).count()
        if cq.used_count + reserved < cq.total_count:
            candidate = cq
            break
    if not candidate:
        raise HTTPException(status_code=400, detail=f"該個案於 {appt_date} 無可用機構額度")
    return candidate.id


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    start: datetime | None = None,
    end: datetime | None = None,
    status_filter: str | None = Query(None, alias="status"),
    case_id: int | None = None,
    room_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Appointment).options(
        joinedload(Appointment.case),
        joinedload(Appointment.therapist),
        joinedload(Appointment.room),
    )
    if user.role == "therapist" and not room_id:
        query = query.filter(Appointment.therapist_id == user.id)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    if case_id:
        query = query.filter(Appointment.case_id == case_id)
    if room_id:
        query = query.filter(Appointment.room_id == room_id)
    if start and end:
        range_filter = f"[{start.isoformat()},{end.isoformat()})"
        query = query.filter(
            text("time_range && :r").bindparams(r=range_filter)
        )
    appointments = query.order_by(Appointment.id.desc()).limit(200).all()

    therapist_ids = list({a.therapist_id for a in appointments})
    therapists = {}
    if therapist_ids:
        users = db.query(User).filter(User.id.in_(therapist_ids)).all()
        therapists = {u.id: u for u in users}

    return [_to_response(a, therapists.get(a.therapist_id), db, viewer=user) for a in appointments]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # accountant cannot create appointments
    if user.role == "accountant":
        raise HTTPException(status_code=403, detail="Accountant cannot create appointments")

    case = db.query(Case).filter(Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # 合療：付款方(case_id)可為伴侶案本身或其成員；心理師一律取伴侶案的共同心理師
    couple = _validate_couple(db, body.couple_case_id, body.case_id)
    therapist_case = couple or case

    # therapist can only create for their own cases
    if user.role == "therapist" and therapist_case.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能為自己的個案建立預約")

    therapist = (
        user if user.role == "therapist"
        else db.query(User).filter(User.id == therapist_case.therapist_id).first()
    )
    if not therapist or not therapist.user_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    if body.session_type == "in_person" and not body.room_id:
        raise HTTPException(status_code=400, detail="Room required for in-person sessions")

    if body.room_id:
        _check_room_conflict(db, body.room_id, body.start_time, body.end_time)

    number = _next_appointment_number(db, therapist.user_code, body.start_time)
    visit_seq = _next_visit_seq(db, body.case_id)

    # ── 機構合約子系統整合點（07 §5.2、§7.1）───────────────────────────
    # plan_id 有值 → 走新路徑：跟子系統要報價，額度檢查與計價全部交給它。
    # 否則 → 走舊路徑：case_institution_quotas，行為與改動前完全一致。
    # 兩條路徑互斥，不會同時發生（AppointmentCreate 沒有同時要求兩者的欄位）。
    quote = None
    quota_id = None
    funding_source = body.funding_source
    if body.plan_id:
        quote = get_funding_provider().quote(
            db,
            QuoteRequest(
                case_id=body.case_id,
                plan_id=body.plan_id,
                therapist_id=therapist.id,
                session_type=body.session_type,
                consult_type=body.consult_type,
                location_kind=body.location_kind,
                visit_seq=visit_seq,
                duration_min=int((body.end_time - body.start_time).total_seconds() // 60),
                appt_date=body.start_time.date(),
            ),
        )
        if quote.quota.blocking:
            raise HTTPException(status_code=400, detail=quote.quota.blocking)
        amount = body.amount if body.amount is not None else float(quote.pricing.unit_price)
        funding_source = "institution"  # 機構方案報價一律視為機構案，忽略 body.funding_source
    else:
        if body.amount is None:
            raise HTTPException(status_code=400, detail="amount 為必填（未指定 plan_id 時）")
        amount = body.amount
        quota_id = _resolve_quota(
            db, body.case_id, body.funding_source, body.quota_id, body.start_time.date()
        )

    time_range = DateTimeTZRange(body.start_time, body.end_time)
    appt = Appointment(
        appointment_number=number,
        case_id=body.case_id,
        therapist_id=therapist.id,
        room_id=body.room_id,
        session_type=body.session_type,
        consult_type=body.consult_type,
        location_kind=body.location_kind,
        time_range=time_range,
        amount=amount,
        funding_source=funding_source,
        quota_id=quota_id,
        visit_seq=visit_seq,
        couple_case_id=body.couple_case_id,
        status="booked",
        created_by=user.id,
    )
    if quote is not None:
        appt.plan_id = quote.plan_id
        appt.case_payable = quote.pricing.case_payable
        appt.institution_payable = quote.pricing.institution_payable
        appt.compensation_mode = quote.compensation.mode
        appt.commissionable_base = quote.compensation.commissionable_base
        appt.plan_quote = json.loads(quote.model_dump_json())
    db.add(appt)
    _flush_with_conflict_guard(db)  # 先拿到 appt.id，reserve() 要用；仍在同一交易內，尚未 commit
    if quote is not None:
        get_funding_provider().reserve(db, appt.id, quote)
        # 方案的行政流程提醒落成這一筆預約的可勾選項目（02 §1.2、07 §5.3 ⑥）
        materialize_admin_tasks(db, appt, quote)
    db.commit()
    db.refresh(appt)
    return _to_response(appt, therapist, db)


@router.put("/{appointment_id}/check-in", response_model=AppointmentResponse)
def check_in(
    appointment_id: int,
    body: CheckInRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """P1 出席驅動的核心端點（01 §A1、02 §4.1、08 §5）。

    這是「報到」這件事在系統裡唯一的入口——按「已到」就在這裡立刻建立
    session_record，不再等時間到讓 materialize_due_appointments() 幫你做。
    按「未到」就在這裡處理額度還原，appointment 狀態維持 'booked'（供
    對帳追蹤，定案不轉 cancelled，見 01 §C3）。

    權限（02 §7 權限矩陣）：現場個案的已到/未到由櫃檯（admin/staff）登錄；
    視訊/外展由心理師自己按。管理員兩種都能按（覆蓋用）。
    """
    return perform_check_in(db, appointment_id, body, user)


def _booked_referral_for(db: Session, appointment_id: int):
    """這筆預約是不是某個媒合案還沒報到的初診？是的話回傳那個媒合案。

    只 import 模型、不 import `app.referral.service`——那支反過來會呼叫
    `perform_check_in()`，互相 import 會成環。這裡要的也只是「有沒有」。
    """
    from app.referral.models.referral import Referral  # 區域 import，避免載入順序成環

    return (
        db.query(Referral)
        .filter(Referral.appointment_id == appointment_id, Referral.status == "booked")
        .first()
    )


def perform_check_in(
    db: Session,
    appointment_id: int,
    body: CheckInRequest,
    user: User,
    now: datetime | None = None,
    *,
    first_visit_ok: bool = False,
):
    """check-in 的實作本體。抽出來是為了讓 in-process 呼叫端（媒合子系統的
    referral/service.py、以及灌歷史資料的 generate_fake_data.py）能傳入
    `now`——報到時間戳要跟著那場諮商當時的時間，不是灌資料當下的時間。

    `now` 與 `first_visit_ok` 刻意不放在端點簽名上：FastAPI 會把多出來的參數
    當成 query string，等於開一個「從 HTTP 就能偽造報到時間／繞過初診閘門」的
    洞。留在這一層，HTTP 永遠拿不到。

    **初診閘門**（11 §5.9）：初診預約就是一筆普通的 appointments 列，本來就
    會出現在診間日曆上，而這支函式原本完全不知道媒合案的存在。行政若直接按
    「已到」，預約會變 arrived、場次照常建立——看起來一切正常，但媒合案永遠
    卡在 booked，個案永遠停在 initial：**沒有身分證、也就永遠拿不到病歷號**。
    那條走得通卻會把資料走壞的路，正好是行政最自然會走的那條。所以擋下來，
    指向初診流程；媒合服務自己準備好之後再帶 `first_visit_ok=True` 進來。
    """
    now = now or datetime.now(timezone.utc)

    if not first_visit_ok:
        referral = _booked_referral_for(db, appointment_id)
        if referral:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"這是媒合案 {referral.referral_code} 的初診，需要一併登記身分證以產生病歷號。"
                    "請在診間日曆點「已到」，由初診報到表單完成。"
                ),
            )
    if body.status not in ("arrived", "no_show"):
        raise HTTPException(status_code=400, detail="status 必須是 arrived 或 no_show")

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt.check_in_status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"此預約已經報到過了（目前狀態：{appt.check_in_status}），不能重複操作",
        )
    if appt.status != "booked":
        raise HTTPException(status_code=400, detail=f"此預約狀態為 {appt.status}，無法報到")

    # 權限：現場一律行政/管理員；視訊/外展一律該心理師本人或管理員
    if user.role == "therapist":
        if appt.therapist_id != user.id:
            raise HTTPException(status_code=403, detail="只能為自己的預約報到")
        if appt.session_type == "in_person":
            raise HTTPException(status_code=403, detail="現場個案的已到/未到由櫃檯在診間日曆登錄")
    elif user.role not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if body.status == "no_show":
        appt.check_in_status = "no_show"
        appt.checked_in_at = now
        appt.checked_in_by = user.id
        appt.no_show_reason = body.no_show_reason
        appt.no_show_note = body.no_show_note
        appt.no_show_followup = body.no_show_followup
        # 08 決策 §8.3：未到 = 已預約還原為已預留，不是釋回——個案仍保有額度。
        # 舊 quota_id 路徑目前沒有對應的還原機制（01 §C+ 已記錄的既有缺口，
        # 這輪不擴大範圍去補；機構額度建議走 plan_id 新路徑）。
        if appt.plan_id:
            get_funding_provider().release(db, appt.id, reason=body.no_show_reason or "no_show")
        db.commit()
        db.refresh(appt)
        return _to_response(appt, db.query(User).filter(User.id == appt.therapist_id).first(), db, viewer=user)

    # body.status == "arrived"
    if appt.plan_id:
        try:
            get_funding_provider().consume(db, appt.id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif appt.funding_source == "institution" and appt.quota_id:
        # 舊路徑的原子扣減，與 settlement.py 的邏輯保持一致（見該檔案同一段的說明）
        updated = db.execute(
            text(
                "UPDATE case_institution_quotas SET used_count = used_count + 1 "
                "WHERE id = :qid AND used_count < total_count"
            ),
            {"qid": appt.quota_id},
        ).rowcount
        if updated == 0:
            raise HTTPException(status_code=400, detail="該扣額已用完或被預約鎖定")

    existing = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="此預約已有對應的帳冊紀錄")

    therapist = db.query(User).filter(User.id == appt.therapist_id).first()
    case = db.query(Case).filter(Case.id == appt.case_id).first()
    record = build_session_record(db, appt, case, therapist)
    db.add(record)

    appt.status = "executed"
    appt.check_in_status = "arrived"
    appt.checked_in_at = now
    appt.checked_in_by = user.id

    db.commit()
    db.refresh(appt)
    return _to_response(appt, therapist, db, viewer=user)


def _payable_amount(sr: SessionRecord) -> Decimal:
    """這筆應該向個案收多少：case_payable 有值就用它（機構案的個案自付額），
    否則 fallback 用整筆 amount（純自費/舊機構路徑沒有 case_payable，代表
    整筆都是個案自付）。見 models/session_record.py 的 copay 欄位說明。"""
    return sr.case_payable if sr.case_payable is not None else Decimal(str(sr.amount))


def _next_appointment_receipt_no(db: Session, d: date) -> str:
    """收據編號。格式在 services/numbering.py，預設 v7（A…C021-1），可切回 legacy。

    舊寫法是 receipts 表自己數自己的，跟 session_records 那套各數各的，同一天
    會產出兩個一模一樣的字串。現在兩張表共用同一個配號 scope，不會再重複。"""
    return numbering.next_receipt_no(db, on_date=d)


@router.post("/{appointment_id}/payment-step", response_model=PaymentStepResponse)
def payment_step(
    appointment_id: int,
    body: PaymentStepRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """報到流程步驟2：收款。見 01 §A2、08 §8 下一步第1項。

    只收個案自付額（case_payable，缺省時為全額）——機構那份（
    institution_payable）走既有 /ledger + 機構核銷案容器流程，跟這裡無關。
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
    if not sr:
        raise HTTPException(status_code=400, detail="此預約尚未報到，無法收款")
    if sr.is_void:
        raise HTTPException(status_code=400, detail="此筆紀錄已作廢")
    if sr.copay_collected_at is not None:
        raise HTTPException(status_code=400, detail="已收款過，不能重複操作")

    payable = _payable_amount(sr)
    if payable <= 0:
        raise HTTPException(status_code=400, detail="此筆免收（機構全額或金額為 0），無需收款")

    if body.payment_method not in ("cash", "transfer"):
        raise HTTPException(status_code=400, detail="請選擇收款方式（現金或匯款）")
    note = body.payment_note.strip() if body.payment_note else None
    if body.payment_method == "transfer" and not note:
        raise HTTPException(status_code=400, detail="匯款資訊為必填（如帳戶末五碼）")

    now = datetime.now(timezone.utc)
    sr.copay_collected_at = now
    sr.copay_payment_method = body.payment_method
    sr.copay_payment_note = note

    # 純自費案（無機構那份）同步既有 payment_status，讓 /ledger 既有頁面
    # 也看得到正確狀態——機構案的 payment_status 語意是「機構請款進度」，
    # 不動它（見 models/session_record.py 的說明）。
    if (sr.institution_payable is None or sr.institution_payable == 0) and sr.payment_status == "unpaid":
        sr.payment_status = "paid"
        sr.paid_at = now
        sr.payment_method = body.payment_method
        sr.payment_note = note

    db.commit()
    db.refresh(sr)
    return PaymentStepResponse(
        session_record_id=sr.id,
        payable_amount=float(payable),
        copay_collected_at=sr.copay_collected_at,
        copay_payment_method=sr.copay_payment_method,
        copay_payment_note=sr.copay_payment_note,
    )


@router.post("/{appointment_id}/receipt", response_model=IssueReceiptResponse, status_code=status.HTTP_201_CREATED)
def issue_receipt(
    appointment_id: int,
    body: IssueReceiptRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """報到流程步驟3：開立收據。見 01 §A2。"""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
    if not sr:
        raise HTTPException(status_code=400, detail="此預約尚未報到，無法開立收據")
    if sr.copay_collected_at is None:
        raise HTTPException(status_code=400, detail="尚未收款，無法開立收據")

    existing = db.query(Receipt).filter(Receipt.session_record_id == sr.id, Receipt.status == "issued").first()
    if existing:
        raise HTTPException(status_code=400, detail=f"此筆已開立過收據（{existing.receipt_no}）")

    if not body.fee_item_id and not (body.fee_item_custom_name and body.fee_item_custom_name.strip()):
        raise HTTPException(status_code=400, detail="請選擇收款項目，或填寫自訂項目名稱")

    fee_item_name = None
    fee_item_custom_name = None
    if body.fee_item_id:
        fi = db.query(FeeItem).filter(FeeItem.id == body.fee_item_id, FeeItem.is_active.is_(True)).first()
        if not fi:
            raise HTTPException(status_code=404, detail="收費項目不存在或已停用")
        fee_item_name = fi.name
    else:
        fee_item_custom_name = body.fee_item_custom_name.strip()
        fee_item_name = fee_item_custom_name  # 未歸類，畫面顯示用自訂名稱本身

    payable = _payable_amount(sr)
    receipt = Receipt(
        receipt_no=_next_appointment_receipt_no(db, sr.session_date),
        session_record_id=sr.id,
        amount=payable,
        fee_item_id=body.fee_item_id,
        fee_item_custom_name=fee_item_custom_name,
        note=body.note.strip() if body.note else None,
        created_by=user.id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return IssueReceiptResponse(
        id=receipt.id,
        receipt_no=receipt.receipt_no,
        amount=float(receipt.amount),
        fee_item_name=fee_item_name,
        note=receipt.note,
        status=receipt.status,
        created_at=receipt.created_at,
    )


@router.post("/batch", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
def create_batch(
    body: AppointmentBatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "accountant":
        raise HTTPException(status_code=403, detail="Accountant cannot create appointments")

    case = db.query(Case).filter(Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    couple = _validate_couple(db, body.couple_case_id, body.case_id)
    therapist_case = couple or case

    if user.role == "therapist" and therapist_case.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能為自己的個案建立預約")

    therapist = (
        user if user.role == "therapist"
        else db.query(User).filter(User.id == therapist_case.therapist_id).first()
    )
    if not therapist or not therapist.user_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    batch_id = str(uuid.uuid4())[:8]
    next_vs = _next_visit_seq(db, body.case_id)
    results = []

    for i, slot in enumerate(body.slots):
        visit_seq = next_vs + i
        slot_funding = slot.funding_source or body.funding_source
        slot_quota = slot.quota_id if slot.quota_id is not None else (
            body.quota_id if slot.funding_source is None else None
        )

        if body.room_id:
            _check_room_conflict(db, body.room_id, slot.start_time, slot.end_time)

        # 機構方案批次（原本完全沒有這條路，機構案只能一筆一筆打 POST /appointments）。
        # 逐筆報價而不是報一次沿用：分級計價（visit_seq）與週期子上限都跟「第幾次」
        # 有關，整批共用同一份報價會把第 2 次之後的價錢全部算成第 1 次的。
        quote = None
        quota_id = None
        if body.plan_id:
            quote = get_funding_provider().quote(
                db,
                QuoteRequest(
                    case_id=body.case_id,
                    plan_id=body.plan_id,
                    therapist_id=therapist.id,
                    session_type=body.session_type,
                    consult_type=body.consult_type,
                    location_kind=body.location_kind,
                    visit_seq=visit_seq,
                    duration_min=int((slot.end_time - slot.start_time).total_seconds() // 60),
                    appt_date=slot.start_time.date(),
                ),
            )
            if quote.quota.blocking:
                raise HTTPException(
                    status_code=400,
                    detail=f"第 {i + 1} 筆（{slot.start_time.date()}）：{quote.quota.blocking}",
                )
            amount = slot.amount if slot.amount is not None else float(quote.pricing.unit_price)
            slot_funding = "institution"
        else:
            amount = slot.amount if slot.amount is not None else body.amount
            if amount is None:
                raise HTTPException(status_code=400, detail="amount 為必填（未指定 plan_id 時）")
            quota_id = _resolve_quota(
                db, body.case_id, slot_funding, slot_quota, slot.start_time.date()
            )

        number = _next_appointment_number(db, therapist.user_code, slot.start_time)
        time_range = DateTimeTZRange(slot.start_time, slot.end_time)

        appt = Appointment(
            appointment_number=number,
            case_id=body.case_id,
            therapist_id=therapist.id,
            room_id=body.room_id,
            session_type=body.session_type,
            consult_type=body.consult_type,
            location_kind=body.location_kind,
            time_range=time_range,
            amount=amount,
            funding_source=slot_funding,
            quota_id=quota_id,
            visit_seq=visit_seq,
            couple_case_id=body.couple_case_id,
            status="booked",
            batch_id=batch_id,
            created_by=user.id,
        )
        if quote is not None:
            appt.plan_id = quote.plan_id
            appt.case_payable = quote.pricing.case_payable
            appt.institution_payable = quote.pricing.institution_payable
            appt.compensation_mode = quote.compensation.mode
            appt.commissionable_base = quote.compensation.commissionable_base
            appt.plan_quote = json.loads(quote.model_dump_json())
        db.add(appt)
        _flush_with_conflict_guard(db)
        if quote is not None:
            get_funding_provider().reserve(db, appt.id, quote)
            materialize_admin_tasks(db, appt, quote)
        results.append(appt)

    db.commit()
    for a in results:
        db.refresh(a)
    return [_to_response(a, therapist, db) for a in results]


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    appointment_id: int,
    body: AppointmentUpdate,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"只能編輯 booked 狀態的預約，目前狀態：{a.status}")

    before = {
        "room_id": a.room_id, "session_type": a.session_type,
        "amount": float(a.amount), "funding_source": a.funding_source,
        "quota_id": a.quota_id, "time_range": str(a.time_range),
    }

    if body.start_time is not None or body.end_time is not None:
        new_start = body.start_time or a.time_range.lower
        new_end = body.end_time or a.time_range.upper
        room_id = body.room_id if body.room_id is not None else a.room_id
        if room_id:
            _check_room_conflict(db, room_id, new_start, new_end, exclude_id=appointment_id)
        a.time_range = DateTimeTZRange(new_start, new_end)

    if body.room_id is not None:
        a.room_id = body.room_id
    if body.session_type is not None:
        a.session_type = body.session_type
    if body.amount is not None:
        a.amount = body.amount
    if body.funding_source is not None:
        a.funding_source = body.funding_source
    if body.quota_id is not None:
        a.quota_id = body.quota_id

    # 先 flush 讓 EXCLUDE 約束有機會攔截時間/診間變更造成的衝突，
    # 確認沒問題才寫 audit log、才 commit（見 _flush_with_conflict_guard）。
    _flush_with_conflict_guard(db)

    after = {
        "room_id": a.room_id, "session_type": a.session_type,
        "amount": float(a.amount), "funding_source": a.funding_source,
        "quota_id": a.quota_id, "time_range": str(a.time_range),
    }
    write_audit(db, "appointments", a.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.put("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return perform_cancel(db, appointment_id, user)


def perform_cancel(db: Session, appointment_id: int, user: User, now: datetime | None = None):
    """取消預約的實作本體。`now` 同 perform_check_in()：留給 in-process 呼叫端
    （灌歷史資料）用，不放在端點簽名上以免變成可從 HTTP 偽造的 query 參數。"""
    now = now or datetime.now(timezone.utc)
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"Cannot cancel appointment with status '{a.status}'")

    appt_date = a.time_range.lower.date() if a.time_range else None
    if appt_date and appt_date < now.date():
        raise HTTPException(status_code=400, detail="Cannot cancel past appointments")

    if a.time_range and a.time_range.upper is not None:
        cutoff = a.time_range.upper - timedelta(minutes=SETTLEMENT_LEAD_MINUTES)
        if now >= cutoff:
            cutoff_local = cutoff.astimezone().strftime("%Y-%m-%d %H:%M")
            raise HTTPException(
                status_code=400,
                detail=f"已逾可取消時限（{cutoff_local}），請洽行政協助處理",
            )

    a.status = "cancelled"
    # 機構額度歸還：reserve() 在建立預約時扣掉了 reserved_count，取消時要還回去，
    # 否則三態恆等式（quota_limit + extended = used + reserved + booked）每取消
    # 一次就少 1，合約面板的三色長條會愈算愈短。見 models/enrollment.py 的恆等式。
    if a.plan_id:
        get_funding_provider().release(db, a.id, reason="cancelled", bill_no_show_fee=False)
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"status": "booked"}, {"status": "cancelled"})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.put("/{appointment_id}/payment", response_model=AppointmentResponse)
def update_appointment_payment(
    appointment_id: int,
    body: AppointmentPaymentUpdate,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if a.status != "booked":
        raise HTTPException(status_code=400, detail="僅未結算的預約可改付款方式")

    appt_date = a.time_range.lower.date() if a.time_range else date.today()
    new_quota_id = _resolve_quota(db, a.case_id, body.funding_source, body.quota_id, appt_date)

    before = {"funding_source": a.funding_source, "quota_id": a.quota_id}
    a.funding_source = body.funding_source
    a.quota_id = new_quota_id
    write_audit(
        db, "appointments", a.id, "UPDATE", user.id,
        before,
        {"funding_source": a.funding_source, "quota_id": a.quota_id},
    )
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


class BatchDeleteRequest(BaseModel):
    ids: list[int]


def _can_delete(a: Appointment, user: User, db: Session) -> str | None:
    """Return an error message if the appointment cannot be deleted, else None."""
    if user.role == "therapist" and a.therapist_id != user.id:
        return "存取被拒"
    if a.status != "booked":
        return f"狀態為「{a.status}」的預約無法刪除"
    sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == a.id).first()
    if sr:
        return "已產生帳冊紀錄，無法刪除"
    if a.time_range and a.time_range.upper is not None:
        cutoff = a.time_range.upper - timedelta(minutes=SETTLEMENT_LEAD_MINUTES)
        if datetime.now(timezone.utc) >= cutoff:
            return f"已逾可取消時限（{cutoff.astimezone().strftime('%Y-%m-%d %H:%M')}）"
    return None


@router.delete("")
def batch_delete_appointments(
    body: BatchDeleteRequest,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="未選擇任何預約")
    appts = db.query(Appointment).filter(Appointment.id.in_(body.ids)).all()
    found_ids = {a.id for a in appts}
    missing = [i for i in body.ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"預約不存在：{missing}")
    for a in appts:
        err = _can_delete(a, user, db)
        if err:
            raise HTTPException(status_code=400, detail=f"預約 {a.appointment_number}: {err}")
    deleted = []
    for a in appts:
        # 刪除等同取消：機構額度要還回 reserved，否則三態恆等式每刪一筆少 1。
        # 不收未到補助（見 funding/ports.py release 的 bill_no_show_fee 說明）。
        if a.plan_id:
            get_funding_provider().release(db, a.id, reason="deleted", bill_no_show_fee=False)
        write_audit(db, "appointments", a.id, "DELETE", user.id,
                    {"appointment_number": a.appointment_number, "status": a.status}, None)
        deleted.append(a.id)
        db.delete(a)
    db.commit()
    return {"deleted": len(deleted), "ids": deleted}


@router.delete("/batch")
def delete_by_batch_id(
    batch_id: str = Query(...),
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    appts = db.query(Appointment).filter(Appointment.batch_id == batch_id).all()
    if not appts:
        raise HTTPException(status_code=404, detail="找不到此批次預約")
    for a in appts:
        err = _can_delete(a, user, db)
        if err:
            raise HTTPException(status_code=400, detail=f"預約 {a.appointment_number}: {err}")
    deleted = []
    for a in appts:
        if a.plan_id:
            get_funding_provider().release(db, a.id, reason="deleted", bill_no_show_fee=False)
        write_audit(db, "appointments", a.id, "DELETE", user.id,
                    {"appointment_number": a.appointment_number, "batch_id": batch_id}, None)
        deleted.append(a.id)
        db.delete(a)
    db.commit()
    return {"deleted": len(deleted), "ids": deleted}


class AmountUpdate(BaseModel):
    amount: Decimal


@router.put("/{appointment_id}/amount", response_model=AppointmentResponse)
def update_amount(
    appointment_id: int,
    body: AmountUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Therapist or admin can update amount on their own booked (future) appointments."""
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Therapist can only modify own; admin can modify any
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能修改自己的預約金額")
    if user.role not in ("therapist", "admin"):
        raise HTTPException(status_code=403, detail="Only therapist or admin can update amount")

    if a.status != "booked":
        raise HTTPException(status_code=400, detail="只能修改尚未執行的預約金額")

    # Cannot modify past appointments
    appt_date = a.time_range.lower.date() if a.time_range else None
    if appt_date and appt_date < date.today():
        raise HTTPException(status_code=400, detail="無法修改已過去的預約金額")

    old_amount = float(a.amount) if a.amount else 0
    a.amount = body.amount
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"amount": old_amount}, {"amount": float(body.amount)})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


def _check_room_conflict(db: Session, room_id: int, start: datetime, end: datetime, exclude_id: int | None = None):
    """應用層檢查——目的是給使用者<b>快速、清楚</b>的擋錯訊息。這層有 TOCTOU
    競態窗口（SELECT 之後、INSERT 之前，另一個請求可能插隊），真正保證不會
    撞號的是 DB 層的 EXCLUDE 約束（見 aa5a2b3c4d5f5 migration + 下面的
    _flush_with_conflict_guard()）。兩層並存：這層給人看的訊息、那層給
    正確性的保證。

    P4 起診間還會被「場地租借」佔用，所以改走 services/room_occupancy 一起
    查兩張表——跨表沒辦法用單一 EXCLUDE 約束表達，只能在這一層擋。
    """
    room_occupancy.assert_free(db, room_id, start, end, exclude_appointment_id=exclude_id)


def _flush_with_conflict_guard(db: Session):
    """01 §C5、08 §8：db.flush() 的薄封裝，把 EXCLUDE USING GIST 約束觸發的
    IntegrityError 轉成跟 _check_room_conflict() 一樣的 409，而不是讓
    Postgres 的原始例外訊息（一大串 SQL）洩漏到 API 回應。

    這是應用層檢查沒擋住的漏網之魚才會走到這裡——兩個請求幾乎同時通過
    _check_room_conflict() 的 SELECT，但只有一個能真的 INSERT 成功；
    另一個在這裡被 DB 攔下來。正常情況下（沒有真併發）這裡永遠不會觸發。
    """
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "excl_room_time_overlap" in str(e.orig):
            raise HTTPException(
                status_code=409,
                detail="Room time slot conflict（資料庫層攔截：兩個請求同時搶到同一診間時段，請重新整理後再試一次）",
            )
        raise


# ─────────────────────────────────────────────────────────────────────────
# P4：加時 / 視訊連結 / 個案請假 / 行政流程提醒
# ─────────────────────────────────────────────────────────────────────────

class AdjustDurationRequest(BaseModel):
    """調整實際執行時數（01 §C1、04 §2.4）。收款前使用。"""
    actual_start: datetime
    actual_end: datetime
    note: str | None = None
    recalculate_amount: bool = True


@router.put("/{appointment_id}/adjust-duration", response_model=AppointmentResponse)
def adjust_duration(
    appointment_id: int,
    body: AdjustDurationRequest,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    """加時／縮短：改寫實際起訖、依單價重算金額，並**同步回寫預約時間**。

    01 §C1 裁示：回寫後若與相鄰預約（或場地租借）重疊，直接擋下，畫面提示
    請心理師聯絡行政處理——系統不會自動把下一位擠掉。這是刻意的：把衝突
    交給人去喬，比系統偷偷改別人的預約安全。
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and appt.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能調整自己的預約")
    if appt.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的預約不能調整時數")

    sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
    if sr and sr.copay_collected_at is not None:
        raise HTTPException(status_code=400, detail="已收款，不能再調整時數（請先作廢該筆帳款）")
    if body.actual_end <= body.actual_start:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")

    minutes = int((body.actual_end - body.actual_start).total_seconds() // 60)
    if minutes < 15 or minutes > 480:
        raise HTTPException(status_code=400, detail="實際時數需介於 15 分鐘至 8 小時之間")

    # 回寫前先確認新的時段沒撞到別人（含場地租借）
    if appt.room_id:
        room_occupancy.assert_free(
            db, appt.room_id, body.actual_start, body.actual_end,
            exclude_appointment_id=appt.id,
        )

    before = {
        "time_range": str(appt.time_range), "amount": float(appt.amount),
        "actual_start": appt.actual_start, "actual_end": appt.actual_end,
    }
    old_minutes = 60
    if appt.time_range and appt.time_range.upper and appt.time_range.lower:
        old_minutes = max(1, int((appt.time_range.upper - appt.time_range.lower).total_seconds() // 60))

    appt.actual_start = body.actual_start
    appt.actual_end = body.actual_end
    appt.duration_adjusted_at = datetime.now(timezone.utc)
    appt.duration_adjusted_by = user.id
    appt.duration_note = body.note
    appt.time_range = DateTimeTZRange(body.actual_start, body.actual_end)

    if body.recalculate_amount:
        # 依原本的「每分鐘單價」等比換算。用單價而不是重新報價，是因為機構
        # 報價含分級/額度判斷，重跑會把 visit_seq 之類的情境再算一次；這裡
        # 要的只是「同一個價目、時間變了」。
        unit_per_min = Decimal(str(appt.amount)) / Decimal(old_minutes)
        appt.amount = (unit_per_min * Decimal(minutes)).quantize(Decimal("1"))
        # 機構案還要重新切分兩份金額，否則 case_payable + institution_payable
        # 就不等於 amount 了——收款會收錯、核銷也會請錯。
        # 切法：**個案自付額固定不動**（那是每次固定的部分負擔），時間變動
        # 的部分由機構吸收，institution_payable 補到差額。
        if appt.institution_payable is not None:
            case_part = Decimal(str(appt.case_payable or 0))
            appt.institution_payable = max(Decimal("0"), Decimal(str(appt.amount)) - case_part)
        if appt.commissionable_base is not None:
            base_per_min = Decimal(str(appt.commissionable_base)) / Decimal(old_minutes)
            appt.commissionable_base = (base_per_min * Decimal(minutes)).quantize(Decimal("0.01"))

    _flush_with_conflict_guard(db)

    # 帳冊已存在（已報到）就同步金額與日期，否則日報表會跟預約對不起來
    if sr:
        sr.amount = appt.amount
        sr.institution_payable = appt.institution_payable
        sr.commissionable_base = appt.commissionable_base
        sr.session_date = to_local_date(body.actual_start)

    write_audit(db, "appointments", appt.id, "UPDATE", user.id, before, {
        "time_range": str(appt.time_range), "amount": float(appt.amount),
        "actual_minutes": minutes, "note": body.note,
    }, reason="調整實際執行時數")
    db.commit()
    db.refresh(appt)
    return _to_response(appt, db.query(User).filter(User.id == appt.therapist_id).first(), db, viewer=user)


class VideoLinkRequest(BaseModel):
    video_link: str


@router.put("/{appointment_id}/video-link", response_model=AppointmentResponse)
def set_video_link(
    appointment_id: int,
    body: VideoLinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """心理師自行貼上視訊連結（定稿明確排除「系統自動產生」）。貼上之後
    行政端會看到「待轉發」，轉發完再按下面那支端點記時間。"""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and appt.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能設定自己的預約")
    elif user.role not in ("admin", "staff", "therapist"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if appt.session_type != "online":
        raise HTTPException(status_code=400, detail="只有視訊預約需要連結")

    appt.video_link = body.video_link.strip() or None
    appt.video_forwarded_at = None  # 換了連結就要重新轉發
    appt.video_forwarded_by = None
    write_audit(db, "appointments", appt.id, "UPDATE", user.id, None, {"video_link": appt.video_link})
    db.commit()
    db.refresh(appt)
    return _to_response(appt, db.query(User).filter(User.id == appt.therapist_id).first(), db, viewer=user)


@router.put("/{appointment_id}/video-forwarded", response_model=AppointmentResponse)
def mark_video_forwarded(
    appointment_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """行政把連結轉發給個案之後按這裡。心理師端才看得出來「行政已經寄出去了」。"""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if not appt.video_link:
        raise HTTPException(status_code=400, detail="尚未有視訊連結可轉發")
    appt.video_forwarded_at = datetime.now(timezone.utc)
    appt.video_forwarded_by = user.id
    db.commit()
    db.refresh(appt)
    return _to_response(appt, db.query(User).filter(User.id == appt.therapist_id).first(), db, viewer=user)


class LeaveRequest(BaseModel):
    reason: str | None = None


@router.put("/{appointment_id}/leave", response_model=AppointmentResponse)
def case_leave(
    appointment_id: int,
    body: LeaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """個案請假（心理師端「為此次預約請假」，原因選填）。

    與「未到」是兩件事：請假是事前知道的，時段要釋出、不產生應收、也**不**
    收機構未到補助——補助補的是個案沒出現，不是這場沒發生。所以走
    release(bill_no_show_fee=False)，跟取消同一條路。
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and appt.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能為自己的預約請假")
    elif user.role not in ("admin", "staff", "therapist"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if appt.status != "booked":
        raise HTTPException(status_code=400, detail=f"此預約狀態為 {appt.status}，無法請假")
    if appt.check_in_status != "pending":
        raise HTTPException(status_code=400, detail="已報到過的預約不能改成請假")

    appt.status = "cancelled"
    appt.leave_reason = (body.reason or "").strip() or None
    appt.leave_at = datetime.now(timezone.utc)
    appt.leave_by = user.id
    if appt.plan_id:
        get_funding_provider().release(db, appt.id, reason="case_leave", bill_no_show_fee=False)
    write_audit(db, "appointments", appt.id, "UPDATE", user.id,
                {"status": "booked"}, {"status": "cancelled", "leave_reason": appt.leave_reason},
                reason="個案請假")
    db.commit()
    db.refresh(appt)
    return _to_response(appt, db.query(User).filter(User.id == appt.therapist_id).first(), db, viewer=user)


class AdminTaskResponse(BaseModel):
    id: int
    title: str
    side: str
    sort_order: int
    is_done: bool
    done_at: datetime | None = None
    done_by_name: str | None = None


def _task_to_response(t: AppointmentAdminTask) -> AdminTaskResponse:
    name = t.done_by_name or (t.done_user.name if t.done_user else None)
    return AdminTaskResponse(
        id=t.id, title=t.title, side=t.side, sort_order=t.sort_order,
        is_done=t.is_done, done_at=t.done_at, done_by_name=name,
    )


def materialize_admin_tasks(db: Session, appt: Appointment, quote) -> None:
    """建立預約時，把方案的行政流程提醒清單落成這一筆預約的可勾選項目。

    inst_plans 上的 admin_checklist / therapist_checklist 是「這個方案每次
    要辦哪些事」的範本（JSON 字串陣列），報價時會跟著 Quote 帶出來。範本
    本身沒辦法記「誰在什麼時候辦好了」，所以每次預約要複製一份實例。

    診間日曆的方塊要「整格轉灰」有三個條件，其中一個就是這些事項全部勾完
    ——沒有這張表，那個條件永遠不會成立。
    """
    if quote is None:
        return
    checklists = getattr(quote, "checklists", None)
    if checklists is None:
        return
    order = 0
    for side, items in (("admin", checklists.admin or []),
                        ("therapist", checklists.therapist or [])):
        for title in items:
            order += 1
            db.add(AppointmentAdminTask(
                appointment_id=appt.id, title=str(title), side=side, sort_order=order,
            ))


@router.get("/{appointment_id}/admin-tasks", response_model=list[AdminTaskResponse])
def list_admin_tasks(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and appt.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return [_task_to_response(t) for t in appt.admin_tasks]


class ToggleTaskRequest(BaseModel):
    is_done: bool
    actor_name: str | None = None  # 共用帳號（實習心理師）自填姓名


@router.put("/admin-tasks/{task_id}", response_model=AdminTaskResponse)
def toggle_admin_task(
    task_id: int,
    body: ToggleTaskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """就地勾選，記錄執行人與時間（畫面顯示成「✓ 林怡君 08/19 09:12」）。

    權限依 side 切開：admin 側的項目櫃台勾、therapist 側的心理師勾；
    管理員兩邊都能勾（覆蓋用）。
    """
    task = db.query(AppointmentAdminTask).filter(AppointmentAdminTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="找不到此提醒項目")

    if user.role == "therapist":
        if task.appointment.therapist_id != user.id:
            raise HTTPException(status_code=403, detail="只能勾選自己預約的項目")
        if task.side != "therapist":
            raise HTTPException(status_code=403, detail="這是行政端的事項，請由櫃台勾選")
    elif user.role == "staff" and task.side != "admin":
        raise HTTPException(status_code=403, detail="這是心理師端的事項，請由心理師勾選")
    elif user.role not in ("admin", "staff", "therapist"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    task.is_done = body.is_done
    if body.is_done:
        task.done_at = datetime.now(timezone.utc)
        task.done_by = user.id
        task.done_by_name = (body.actor_name or "").strip() or None
    else:
        task.done_at = None
        task.done_by = None
        task.done_by_name = None
    db.commit()
    db.refresh(task)
    return _task_to_response(task)


# ─────────────────────────────────────────────────────────────────────────
# P5：收據作廢 / 重印
#
# receipts 的 status/void_reason/voided_at/voided_by 四個欄位從建表以來
# 沒有任何程式碼寫過——開得出收據，但作廢與重印一直只能靠人工。
# 編號規則見 services/numbering.py：作廢與重印沿用同一個 base，尾碼
# -1 開立 / -2 重印 / -3 作廢，所以同一張收據的三種版本天生串得起來。
# ─────────────────────────────────────────────────────────────────────────

class VoidReceiptRequest(BaseModel):
    reason: str
    reissue: bool = True  # 作廢後是否立刻重開一張（多數情境是開錯要重來）


class ReceiptDetail(BaseModel):
    id: int
    receipt_no: str
    session_record_id: int | None = None
    amount: float
    fee_item_name: str | None = None
    note: str | None = None
    status: str
    void_reason: str | None = None
    created_at: datetime | None = None


def _receipt_detail(db: Session, r: Receipt) -> ReceiptDetail:
    name = r.fee_item_custom_name
    if r.fee_item_id:
        item = db.query(FeeItem).filter(FeeItem.id == r.fee_item_id).first()
        name = item.name if item else name
    return ReceiptDetail(
        id=r.id, receipt_no=r.receipt_no, session_record_id=r.session_record_id,
        amount=float(r.amount), fee_item_name=name, note=r.note, status=r.status,
        void_reason=r.void_reason, created_at=r.created_at,
    )


@router.get("/{appointment_id}/receipts", response_model=list[ReceiptDetail])
def list_appointment_receipts(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """這筆預約開過的所有收據（含已作廢與重印版本）——收據面板要看得到完整軌跡。"""
    sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appointment_id).first()
    if sr is None:
        return []
    rows = db.query(Receipt).filter(Receipt.session_record_id == sr.id).order_by(Receipt.id).all()
    return [_receipt_detail(db, r) for r in rows]


@router.put("/receipts/{receipt_id}/void", response_model=list[ReceiptDetail])
def void_receipt(
    receipt_id: int,
    body: VoidReceiptRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """作廢收據，可選擇同時重開一張。回傳這筆場次的完整收據軌跡。"""
    r = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="找不到此收據")
    if r.status == "voided":
        raise HTTPException(status_code=400, detail="此收據已作廢")
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="作廢收據必須填寫原因")

    sr = db.query(SessionRecord).filter(SessionRecord.id == r.session_record_id).first()
    r.status = "voided"
    r.void_reason = body.reason.strip()
    r.voided_at = datetime.now(timezone.utc)
    r.voided_by = user.id
    r.receipt_no = numbering.receipt_variant(r.receipt_no, numbering.RECEIPT_STATE_VOID)

    if body.reissue and sr is not None:
        db.add(Receipt(
            receipt_no=numbering.next_receipt_no(db, on_date=sr.session_date),
            session_record_id=sr.id, amount=r.amount,
            fee_item_id=r.fee_item_id, fee_item_custom_name=r.fee_item_custom_name,
            note=f"原 {r.receipt_no} 作廢後重開", status="issued", created_by=user.id,
        ))
    write_audit(db, "receipts", r.id, "VOID", user.id, {"status": "issued"},
                {"status": "voided", "reissued": body.reissue}, reason=r.void_reason)
    db.commit()
    if sr is None:
        return [_receipt_detail(db, r)]
    rows = db.query(Receipt).filter(Receipt.session_record_id == sr.id).order_by(Receipt.id).all()
    return [_receipt_detail(db, x) for x in rows]


@router.post("/receipts/{receipt_id}/reprint", response_model=ReceiptDetail, status_code=201)
def reprint_receipt(
    receipt_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """重印：原件仍然有效，另開一張尾碼 -2 的重印版本。

    與作廢的差別就在這裡——作廢是「這張不算數」，重印是「同一張再給一份」。
    共用 base 讓兩者天生串得起來，不必另外建一張重印紀錄表。
    """
    r = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="找不到此收據")
    if r.status == "voided":
        raise HTTPException(status_code=400, detail="已作廢的收據不能重印，請重新開立")

    copy = Receipt(
        receipt_no=numbering.receipt_variant(r.receipt_no, numbering.RECEIPT_STATE_REPRINT),
        session_record_id=r.session_record_id, amount=r.amount,
        fee_item_id=r.fee_item_id, fee_item_custom_name=r.fee_item_custom_name,
        note="補印", status="issued", created_by=user.id,
    )
    db.add(copy)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="此收據已經補印過了")
    write_audit(db, "receipts", r.id, "REPRINT", user.id, None, {"reprint_no": copy.receipt_no})
    db.commit()
    db.refresh(copy)
    return _receipt_detail(db, copy)
