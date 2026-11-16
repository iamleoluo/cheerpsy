import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from psycopg2.extras import DateTimeTZRange
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.models.institution_plan import InstitutionPlan, PlanRateItem, PlanTransportFee
from app.models.case_institution_quota import CaseInstitutionQuota
from app.services import appt_billing
from app.services.audit import write_audit
from app.services.slot_check import assert_room_active, assert_room_free, flush_or_409
from app.schemas.appointment import (
    AppointmentBatchCreate,
    AppointmentCreate,
    AppointmentPaymentUpdate,
    AppointmentResponse,
    AppointmentUpdate,
)

CONSULT_TYPES = ("individual", "couple", "family", "parenting")

router = APIRouter(prefix="/appointments", tags=["appointments"])

# 結束前這段時間內不可取消／刪除（原本借用 settlement 的常數；上線 A 起不再依賴 settlement）
CANCEL_LEAD_MINUTES = 20

def _make_number(therapist_code: str, dt: datetime, seq: int) -> str:
    date_str = dt.strftime("%Y%m%d")
    return f"R-{date_str}-{therapist_code}-{seq:03d}"


def _next_seq(db: Session, therapist_code: str, dt: datetime) -> int:
    date_str = dt.strftime("%Y%m%d")
    prefix = f"R-{date_str}-{therapist_code}-"
    result = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE appointment_number LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar()
    return (result or 0) + 1


def _next_visit_seq(db: Session, case_id: int) -> int:
    current_max = db.query(func.max(Appointment.visit_seq)).filter(
        Appointment.case_id == case_id
    ).scalar()
    return (current_max or 0) + 1


def _to_response(
    a: Appointment,
    therapist: User | None = None,
    db: Session | None = None,
    viewer: User | None = None,
    warnings: list[str] | None = None,
) -> AppointmentResponse:
    start = end = None
    if a.time_range:
        start = a.time_range.lower
        end = a.time_range.upper
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
    # 回應不帶分潤、心理師抽成（那些屬已移除的記帳）；付款方式、額度、方案屬金流資訊，照實回。
    # 金額只是預約上的一個數字。隔離單位是「心理師」不是欄位：行政看全部，心理師看自己的（能走到這裡的
    # 一定是自己的預約，別人的在查詢就被擋掉）。會計維持現狀（記帳已移除，一律 0）。
    can_see_amount = viewer is not None and viewer.role in ("admin", "staff", "therapist")
    quota = appt_billing.quota_summary(db, a.quota_id) if (db is not None and can_see_amount) else None
    plan = rate = tfee = None
    if db is not None and can_see_amount and a.plan_id:
        plan = db.get(InstitutionPlan, a.plan_id)
        rate = db.get(PlanRateItem, a.rate_item_id) if a.rate_item_id else None
        tfee = db.get(PlanTransportFee, a.transport_fee_option_id) if a.transport_fee_option_id else None
    return AppointmentResponse(
        amount=float(a.amount or 0) if can_see_amount else 0,
        funding_source=(a.funding_source or "self_pay") if can_see_amount else None,
        quota_id=a.quota_id if can_see_amount else None,
        quota_institution_name=quota["institution_name"] if quota else None,
        quota_used=quota["used"] if quota else None,
        quota_total=quota["total"] if quota else None,
        quota_remaining=quota["remaining"] if quota else None,
        quota_is_last_session=bool(quota and quota["is_last"]),
        plan_id=a.plan_id if can_see_amount else None,
        plan_name=(plan.name if plan else None) if can_see_amount else None,
        consult_type=a.consult_type if can_see_amount else None,
        service_type=a.service_type if can_see_amount else None,
        rate_item_id=a.rate_item_id if can_see_amount else None,
        rate_item_label=(rate.label if rate else None) if can_see_amount else None,
        # 自付額：自費＝全額；機構 NULL＝未設定（舊資料算不出來，不猜）
        self_pay_amount=(
            (float(a.self_pay_amount) if a.self_pay_amount is not None else None)
            if (a.funding_source or "self_pay") == "institution"
            else float(a.amount or 0)
        ) if can_see_amount else 0,
        institution_name=appt_billing.institution_name_of(db, a, plan, quota) if (db is not None and can_see_amount) else None,
        # 機構補助＝總額 − 自付額（算出來，不存）；自付額未設定時未知
        institution_subsidy=(
            None if a.self_pay_amount is None else max(float(a.amount or 0) - float(a.self_pay_amount), 0.0)
        ) if (can_see_amount and (a.funding_source or "self_pay") == "institution") else None,
        transport_fee_option_id=a.transport_fee_option_id if can_see_amount else None,
        transport_fee_label=(tfee.label if tfee else None) if can_see_amount else None,
        transport_fee=float(a.transport_fee or 0) if can_see_amount else 0,
        warnings=warnings or [],
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
        start_time=start,
        end_time=end,
        visit_seq=a.visit_seq,
        status=a.status,
        batch_id=a.batch_id,
        created_at=a.created_at,
        # Phase 3
        checkin_status=a.checkin_status,
        checked_in_at=a.checked_in_at,
        no_show_type=a.no_show_type,
        video_link=a.video_link,
        notify_admin_to_forward=a.notify_admin_to_forward,
        forwarded_at=a.forwarded_at,
        outreach_location=a.outreach_location,
        is_intake=a.is_intake,
    )


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _audit_manual_price(db: Session, a: Appointment, price, user: User) -> None:
    """機構案行政手動調整應收：留稽核（誰、方案算出多少、改成多少）。"""
    if price.funding == "institution" and price.manual_adjusted:
        write_audit(db, "appointments", a.id, "UPDATE", user.id,
                    {"amount": float(price.computed_amount or 0)}, {"amount": float(price.amount), "manual": True})


def _appointment_or_404(db: Session, user: User, appointment_id: int) -> Appointment:
    """取預約。心理師只能碰自己的：不存在與「是別人的」回完全相同的 404，不讓人用 id 猜出存在與否。"""
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if a is None or (user.role == "therapist" and a.therapist_id != user.id):
        raise HTTPException(status_code=404, detail="Appointment not found")
    return a


def _case_or_404(db: Session, user: User, case_id: int) -> Case:
    """取個案。心理師只能用自己的個案；別人的與不存在一樣回 404。"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None or (user.role == "therapist" and case.therapist_id != user.id):
        raise HTTPException(status_code=404, detail="Case not found")
    return case


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
    if user.role == "therapist":
        # 心理師只能看到自己的場次（沒有任何例外）。
        # 他人的診間佔用請用 GET /rooms/occupancy：只回時段，不含個人資料。
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

    return [
        _to_response(a, therapists.get(a.therapist_id), db, viewer=user)
        for a in appointments
    ]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _appointment_or_404(db, user, appointment_id)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = _case_or_404(db, user, body.case_id)
    if body.couple_case_id:
        _case_or_404(db, user, body.couple_case_id)  # 別人的伴侶案與不存在一樣回 404

    # 合療：付款方(case_id)可為伴侶案本身或其成員；心理師一律取伴侶案的共同心理師
    couple = _validate_couple(db, body.couple_case_id, body.case_id)
    therapist_case = couple or case

    # therapist can only create for their own cases
    if user.role == "therapist" and therapist_case.therapist_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")

    therapist = (
        user if user.role == "therapist"
        else db.query(User).filter(User.id == therapist_case.therapist_id).first()
    )
    if not therapist or not therapist.user_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    if body.session_type == "in_person" and not body.room_id:
        raise HTTPException(status_code=400, detail="Room required for in-person sessions")

    assert_room_active(db, body.room_id)
    assert_room_free(db, body.room_id, body.start_time, body.end_time)

    seq = _next_seq(db, therapist.user_code, body.start_time)
    number = _make_number(therapist.user_code, body.start_time, seq)
    visit_seq = _next_visit_seq(db, body.case_id)

    funding = body.funding_source or case.funding_source or "self_pay"
    quota, warnings = appt_billing.resolve_quota(
        db, body.case_id, funding, body.quota_id, body.start_time.date()
    )

    consult_type = _consult_type(body.consult_type, case, body.couple_case_id)
    price = appt_billing.compute_pricing(
        db, case_id=body.case_id, funding=funding, quota=quota, plan_id=body.plan_id,
        rate_item_id=body.rate_item_id, transport_option_id=body.transport_fee_option_id,
        session_type=body.session_type, duration_minutes=_minutes(body.start_time, body.end_time),
        manual_amount=body.amount, consult_type=consult_type, service_type=body.service_type,
        start_time=body.start_time,
    )
    warnings = warnings + price.warnings

    time_range = DateTimeTZRange(body.start_time, body.end_time)
    appt = Appointment(
        appointment_number=number,
        case_id=body.case_id,
        therapist_id=therapist.id,
        room_id=body.room_id,
        session_type=body.session_type,
        time_range=time_range,
        consult_type=consult_type,
        service_type=body.service_type,
        amount=price.amount,
        self_pay_amount=price.self_pay,
        funding_source=funding,
        plan_id=price.plan_id,
        rate_item_id=price.rate_item_id,
        transport_fee=price.transport_fee,
        transport_fee_option_id=price.transport_option_id,
        quota_id=quota.id if quota else None,
        visit_seq=visit_seq,
        couple_case_id=body.couple_case_id,
        status="booked",
        created_by=user.id,
    )
    db.add(appt)
    flush_or_409(db, body.room_id, body.start_time, body.end_time)  # 並行寫入由資料庫約束擋下
    appt_billing.hold_quota(quota)  # 已預留 → 已預約（同一交易）
    _audit_manual_price(db, appt, price, user)
    db.commit()
    db.refresh(appt)
    return _to_response(appt, therapist, db, viewer=user, warnings=warnings)


@router.post("/batch", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
def create_batch(
    body: AppointmentBatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = _case_or_404(db, user, body.case_id)
    if body.couple_case_id:
        _case_or_404(db, user, body.couple_case_id)  # 別人的伴侶案與不存在一樣回 404

    couple = _validate_couple(db, body.couple_case_id, body.case_id)
    therapist_case = couple or case

    if user.role == "therapist" and therapist_case.therapist_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")

    therapist = (
        user if user.role == "therapist"
        else db.query(User).filter(User.id == therapist_case.therapist_id).first()
    )
    if not therapist or not therapist.user_code:
        raise HTTPException(status_code=400, detail="Therapist not found or has no code")

    assert_room_active(db, body.room_id)
    batch_id = str(uuid.uuid4())[:8]
    next_vs = _next_visit_seq(db, body.case_id)
    funding = body.funding_source or case.funding_source or "self_pay"
    consult_type = _consult_type(body.consult_type, case, body.couple_case_id)
    results = []
    warns: dict[int, list[str]] = {}

    for i, slot in enumerate(body.slots):
        assert_room_free(db, body.room_id, slot.start_time, slot.end_time)

        seq = _next_seq(db, therapist.user_code, slot.start_time)
        number = _make_number(therapist.user_code, slot.start_time, seq)
        time_range = DateTimeTZRange(slot.start_time, slot.end_time)
        quota, slot_warnings = appt_billing.resolve_quota(
            db, body.case_id, funding, body.quota_id, slot.start_time.date()
        )

        price = appt_billing.compute_pricing(
            db, case_id=body.case_id, funding=funding, quota=quota, plan_id=body.plan_id,
            rate_item_id=body.rate_item_id, transport_option_id=body.transport_fee_option_id,
            session_type=body.session_type, duration_minutes=_minutes(slot.start_time, slot.end_time),
            manual_amount=body.amount, consult_type=consult_type, service_type=body.service_type,
            start_time=slot.start_time,
        )
        slot_warnings = slot_warnings + price.warnings

        appt = Appointment(
            appointment_number=number,
            case_id=body.case_id,
            therapist_id=therapist.id,
            room_id=body.room_id,
            session_type=body.session_type,
            time_range=time_range,
            consult_type=consult_type,
            service_type=body.service_type,
            amount=price.amount,
            self_pay_amount=price.self_pay,
            funding_source=funding,
            plan_id=price.plan_id,
            rate_item_id=price.rate_item_id,
            transport_fee=price.transport_fee,
            transport_fee_option_id=price.transport_option_id,
            quota_id=quota.id if quota else None,
            visit_seq=next_vs + i,
            couple_case_id=body.couple_case_id,
            status="booked",
            batch_id=batch_id,
            created_by=user.id,
        )
        db.add(appt)
        # flush 讓同批次後面的 slot 也能看到前面的佔用（診間衝突檢查）
        flush_or_409(db, body.room_id, slot.start_time, slot.end_time)
        appt_billing.hold_quota(quota)  # 同批次後面的 slot 會看到前面已佔用的額度；額度用完的 slot 只警告、不佔額度
        _audit_manual_price(db, appt, price, user)
        results.append(appt)
        warns[i] = slot_warnings

    db.commit()
    for a in results:
        db.refresh(a)
    return [_to_response(a, therapist, db, viewer=user, warnings=warns.get(i)) for i, a in enumerate(results)]


def _consult_type(given: str | None, case: Case, couple_case_id: int | None) -> str:
    """諮商型態：有指定用指定；沒指定時伴侶案（或合療）為 couple，其餘 individual。"""
    if given:
        if given not in CONSULT_TYPES:
            raise HTTPException(status_code=422, detail=f"consult_type 需為 {list(CONSULT_TYPES)}")
        return given
    return "couple" if (couple_case_id or case.case_type == "couple") else "individual"


def _reprice_after_time_change(db: Session, a: Appointment, user: User, old_start, old_end, new_start, new_end) -> list[str]:
    """改時長／日期後的重新計價。判斷「有沒有手動調整過」：用舊時間再算一次，
    若結果與目前存的價目項目、金額、自付額都一樣，就代表是自動算出來的，可以安全重算。"""
    quota = db.get(CaseInstitutionQuota, a.quota_id) if a.quota_id else None
    common = dict(
        db=db, case_id=a.case_id, funding="institution", quota=quota, plan_id=a.plan_id,
        transport_option_id=a.transport_fee_option_id, session_type=a.session_type,
        manual_amount=None, exclude_appointment_id=a.id,
        consult_type=a.consult_type, service_type=a.service_type, rate_item_id=None,
    )
    try:
        old = appt_billing.compute_pricing(duration_minutes=_minutes(old_start, old_end), start_time=old_start, **common)
    except HTTPException:
        old = None
    untouched = (
        old is not None and old.rate_item_id == a.rate_item_id
        and old.amount == a.amount and old.self_pay == a.self_pay_amount
    )
    if not untouched:
        return ["時間已變更，但金額曾手動調整或價目項目為手動指定，未自動重新計價，請確認金額"]
    try:
        new = appt_billing.compute_pricing(duration_minutes=_minutes(new_start, new_end), start_time=new_start, **common)
    except HTTPException as e:
        return [f"時間已變更，但無法依價目重新計價（{e.detail}），金額維持原樣，請確認"]
    if new.amount == a.amount and new.self_pay == a.self_pay_amount and new.rate_item_id == a.rate_item_id:
        return []
    appt_billing.apply_pricing(a, new)
    return [f"時間已變更，已依價目重新計價：總額 {new.amount}、自付 {new.self_pay if new.self_pay is not None else '未設定'}"]


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    appointment_id: int,
    body: AppointmentUpdate,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    a = _appointment_or_404(db, user, appointment_id)  # 心理師只能改自己的；負責心理師不能經由這裡改派
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"只能編輯 booked 狀態的預約，目前狀態：{a.status}")

    before_range = (a.time_range.lower, a.time_range.upper)
    before = {
        "room_id": a.room_id, "session_type": a.session_type,
        "time_range": str(a.time_range), "amount": float(a.amount or 0),
        "self_pay_amount": float(a.self_pay_amount or 0), "plan_id": a.plan_id,
        "rate_item_id": a.rate_item_id, "transport_fee_option_id": a.transport_fee_option_id,
    }

    # 改期或改房都要重新檢查診間（只改房、不改時間也要檢查）
    new_start = body.start_time or a.time_range.lower
    new_end = body.end_time or a.time_range.upper
    new_room = body.room_id if body.room_id is not None else a.room_id
    if body.room_id is not None and body.room_id != a.room_id:
        assert_room_active(db, body.room_id)  # 換到停用的診間不行；原本就在停用診間的場次維持原樣
    changed = (
        body.start_time is not None or body.end_time is not None or body.room_id is not None
    )
    if changed:
        assert_room_free(db, new_room, new_start, new_end, exclude_appointment_id=appointment_id)
        a.time_range = DateTimeTZRange(new_start, new_end)
    if body.room_id is not None:
        a.room_id = body.room_id
    if body.session_type is not None:
        a.session_type = body.session_type
    flush_or_409(db, a.room_id, new_start, new_end, exclude_appointment_id=appointment_id)
    # 金額與方案：改方案、價目項目、交通費 → 依價目重新計算（快照）；只改金額 → 手動調整
    warnings: list[str] = []
    if body.consult_type is not None:
        a.consult_type = body.consult_type
    if body.service_type is not None:
        a.service_type = body.service_type or None
    repriced = any(v is not None for v in (
        body.plan_id, body.rate_item_id, body.transport_fee_option_id, body.consult_type, body.service_type))
    old_start, old_end = before_range
    time_changed = (new_start, new_end) != (old_start, old_end)
    if repriced or body.amount is not None:
        funding = a.funding_source or "self_pay"
        quota = db.get(CaseInstitutionQuota, a.quota_id) if a.quota_id else None
        same_plan = body.plan_id is None or body.plan_id == a.plan_id
        if repriced and funding == "institution":
            price = appt_billing.compute_pricing(
                db, case_id=a.case_id, funding=funding, quota=quota,
                plan_id=body.plan_id if body.plan_id is not None else a.plan_id,
                # 方案沒換時，沒指定的價目項目、交通費沿用原本的；換方案就重新挑
                rate_item_id=body.rate_item_id if body.rate_item_id is not None else (
                    a.rate_item_id if same_plan and body.consult_type is None and body.service_type is None else None),
                transport_option_id=body.transport_fee_option_id if body.transport_fee_option_id is not None else (
                    a.transport_fee_option_id if same_plan else None),
                session_type=a.session_type, duration_minutes=_minutes(new_start, new_end),
                manual_amount=body.amount, exclude_appointment_id=a.id,
                consult_type=a.consult_type, service_type=a.service_type, start_time=new_start,
            )
            appt_billing.apply_pricing(a, price)
            warnings = price.warnings
            _audit_manual_price(db, a, price, user)
        elif body.amount is not None:
            new_amount = Decimal(str(body.amount))
            plan_row = db.get(InstitutionPlan, a.plan_id) if a.plan_id else None
            if new_amount <= 0 and not (funding == "institution" and plan_row is not None and plan_row.allows_zero_amount):
                raise HTTPException(status_code=422, detail="金額必須大於 0")
            if funding == "institution":
                write_audit(db, "appointments", a.id, "UPDATE", user.id,
                            {"amount": float(a.amount or 0)}, {"amount": float(new_amount), "manual": True})
                if a.self_pay_amount is not None:  # 未設定的自付額維持未設定（不猜）
                    a.self_pay_amount = min(a.self_pay_amount, new_amount)
            else:
                a.self_pay_amount = new_amount  # 自費：個案要付的就是全額
            a.amount = new_amount
    elif time_changed and (a.funding_source or "self_pay") == "institution" and a.plan_id:
        # 改時長／改日期（階梯第幾次可能變）：沒手動調整過的金額依價目重新計價；手動調整過的不動，只提醒
        warnings = _reprice_after_time_change(db, a, user, old_start, old_end, new_start, new_end)

    after = {
        "room_id": a.room_id, "session_type": a.session_type,
        "time_range": str(a.time_range), "amount": float(a.amount or 0),
        "self_pay_amount": float(a.self_pay_amount or 0), "plan_id": a.plan_id,
        "rate_item_id": a.rate_item_id, "transport_fee_option_id": a.transport_fee_option_id,
    }
    write_audit(db, "appointments", a.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user, warnings=warnings)


@router.put("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _appointment_or_404(db, user, appointment_id)
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"Cannot cancel appointment with status '{a.status}'")

    today = date.today()
    appt_date = a.time_range.lower.date() if a.time_range else None
    if appt_date and appt_date < today:
        raise HTTPException(status_code=400, detail="Cannot cancel past appointments")

    if a.time_range and a.time_range.upper is not None:
        cutoff = a.time_range.upper - timedelta(minutes=CANCEL_LEAD_MINUTES)
        now = datetime.now(timezone.utc)
        if now >= cutoff:
            cutoff_local = cutoff.astimezone().strftime("%Y-%m-%d %H:%M")
            raise HTTPException(
                status_code=400,
                detail=f"已逾可取消時限（{cutoff_local}），請洽行政協助處理",
            )

    a.status = "cancelled"
    a.checkin_status = "pending"
    appt_billing.release_quota(db, a.quota_id)  # 已預約 → 退回已預留
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
    """改付款方式（自費／機構）與扣哪一個額度。只動額度與付款方式，不產生任何流水或核銷。"""
    a = _appointment_or_404(db, user, appointment_id)
    if a.status != "booked":
        raise HTTPException(status_code=400, detail="僅尚未執行的預約可改付款方式")
    appt_date = a.time_range.lower.date() if a.time_range else date.today()
    before = {"funding_source": a.funding_source, "quota_id": a.quota_id}
    appt_billing.release_quota(db, a.quota_id)  # 先把舊額度退回，再重新挑（可能挑回同一個）
    a.quota_id = None
    quota, warnings = appt_billing.resolve_quota(db, a.case_id, body.funding_source, body.quota_id, appt_date)
    # 換付款方式 → 重新計價（自費要金額；機構由方案價目帶出，快照）
    price = appt_billing.compute_pricing(
        db, case_id=a.case_id, funding=body.funding_source, quota=quota, plan_id=body.plan_id,
        rate_item_id=body.rate_item_id, transport_option_id=body.transport_fee_option_id,
        session_type=a.session_type, duration_minutes=_minutes(a.time_range.lower, a.time_range.upper),
        manual_amount=body.amount,  # 自費必填；機構不送＝由價目帶出
        exclude_appointment_id=a.id,
        consult_type=a.consult_type, service_type=a.service_type, start_time=a.time_range.lower,
    )
    warnings = warnings + price.warnings
    a.funding_source = body.funding_source
    a.quota_id = quota.id if quota else None
    appt_billing.hold_quota(quota)
    appt_billing.apply_pricing(a, price)
    _audit_manual_price(db, a, price, user)
    write_audit(db, "appointments", a.id, "UPDATE", user.id, before,
                {"funding_source": a.funding_source, "quota_id": a.quota_id,
                 "amount": float(a.amount), "self_pay_amount": float(a.self_pay_amount or 0), "plan_id": a.plan_id})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user, warnings=warnings)


@router.put("/{appointment_id}/collection", status_code=status.HTTP_410_GONE)
def record_collection(user: User = Depends(get_current_user)):
    """收款在行政另一套系統處理；本系統不記收款。欄位（payment_*）保留不刪，端點停用。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="收款記錄已停用（收款在行政另一套系統）")


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
        cutoff = a.time_range.upper - timedelta(minutes=CANCEL_LEAD_MINUTES)
        if datetime.now(timezone.utc) >= cutoff:
            return f"已逾可取消時限（{cutoff.astimezone().strftime('%Y-%m-%d %H:%M')}）"
    return None


def _therapist_cannot_delete(user: User) -> None:
    """刪除只限 admin／staff。心理師只能「取消」自己的預約。"""
    if user.role == "therapist":
        raise HTTPException(status_code=403, detail="心理師不能刪除預約，請改用取消")


@router.delete("")
def batch_delete_appointments(
    body: BatchDeleteRequest,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="未選擇任何預約")
    q = db.query(Appointment).filter(Appointment.id.in_(body.ids))
    if user.role == "therapist":
        q = q.filter(Appointment.therapist_id == user.id)  # 別人的 id 視同不存在
    appts = q.all()
    found_ids = {a.id for a in appts}
    missing = [i for i in body.ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"預約不存在：{missing}")
    _therapist_cannot_delete(user)  # 別人的 id 已在上面視同不存在（404）；到這裡的都是自己的，一律 403
    for a in appts:
        err = _can_delete(a, user, db)
        if err:
            raise HTTPException(status_code=400, detail=f"預約 {a.appointment_number}: {err}")
    deleted = []
    for a in appts:
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
    q = db.query(Appointment).filter(Appointment.batch_id == batch_id)
    if user.role == "therapist":
        q = q.filter(Appointment.therapist_id == user.id)  # 只看得到自己的；別人的批次視同不存在
    appts = q.all()
    if not appts:
        raise HTTPException(status_code=404, detail="找不到此批次預約")
    _therapist_cannot_delete(user)
    for a in appts:
        err = _can_delete(a, user, db)
        if err:
            raise HTTPException(status_code=400, detail=f"預約 {a.appointment_number}: {err}")
    deleted = []
    for a in appts:
        write_audit(db, "appointments", a.id, "DELETE", user.id,
                    {"appointment_number": a.appointment_number, "batch_id": batch_id}, None)
        deleted.append(a.id)
        db.delete(a)
    db.commit()
    return {"deleted": len(deleted), "ids": deleted}


@router.put("/{appointment_id}/amount", status_code=status.HTTP_410_GONE)
def update_amount(user: User = Depends(get_current_user)):
    """帳務拆除上線 A：預約金額已停用，伺服器一律寫 0。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="預約金額功能已停用")


# ---------------------------------------------------------------------------
# 報到
#
# 診間日曆主控台的核心操作。帳務拆除上線 A 起，報到／未到只改預約狀態：
# 不寫 session_records、不動機構額度、不計失約費。
# ---------------------------------------------------------------------------
class CheckInBody(BaseModel):
    """未到時需指定類型（僅記錄，不再計費）。"""

    no_show_type: str | None = None
    note: str | None = None


# 24 小時前請假／臨時取消／無故未到（僅分類，不再有金額）
NO_SHOW_TYPES = ("advance_notice", "late_cancel", "no_notice")


@router.put("/{appointment_id}/arrive", response_model=AppointmentResponse)
def mark_arrived(
    appointment_id: int,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    """初診／一般預約報到「已到」：只轉為已執行，不產生帳務紀錄。心理師只能處理自己的預約。"""
    a = _appointment_or_404(db, user, appointment_id)
    if a.checkin_status == "arrived":
        raise HTTPException(status_code=400, detail="此預約已報到")
    if a.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的預約不可報到")

    a.checkin_status = "arrived"
    a.checked_in_at = datetime.now(timezone.utc)
    a.checked_in_by = user.id
    a.status = "executed"
    appt_billing.consume_quota(db, a.quota_id)  # 已預約 → 已使用
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"},
                {"checkin_status": "arrived"})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.put("/{appointment_id}/no-show-fee", status_code=status.HTTP_410_GONE)
def set_no_show_fee(user: User = Depends(get_current_user)):
    """失約費建議金額已停用（欄位 no_show_fee 保留不刪，一律為 0）。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="失約費功能已停用")


@router.put("/{appointment_id}/absent", response_model=AppointmentResponse)
def mark_absent(
    appointment_id: int,
    body: CheckInBody,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    """報到「未到」：只記錄未到類型，不產生帳務紀錄、不計失約費。心理師只能處理自己的預約。"""
    a = _appointment_or_404(db, user, appointment_id)
    if a.checkin_status == "arrived":
        raise HTTPException(status_code=400, detail="已報到的預約不可改為未到，請洽管理員")
    if body.no_show_type not in NO_SHOW_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"no_show_type 需為 {list(NO_SHOW_TYPES)}",
        )

    a.checkin_status = "absent"
    a.checked_in_at = datetime.now(timezone.utc)
    a.checked_in_by = user.id
    a.status = "no_show"
    a.no_show_type = body.no_show_type
    appt_billing.release_quota(db, a.quota_id)  # 未到：已預約 → 退回已預留
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"},
                {"checkin_status": "absent", "no_show_type": body.no_show_type})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)
