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
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services import quota_flow
from app.services.audit import write_audit
from app.services.settlement import SETTLEMENT_LEAD_MINUTES
from app.schemas.appointment import (
    AppointmentBatchCreate,
    AppointmentCreate,
    AppointmentPaymentUpdate,
    AppointmentResponse,
    AppointmentUpdate,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

DEFAULT_COMMISSION_RATE = Decimal("0.70")


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
    # 機構額度：供日曆標示「最後一次」
    _quota_last, _quota_used, _quota_total = False, None, None
    if a.quota_id and db is not None:
        _q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
        if _q:
            _quota_used, _quota_total = _q.used_count, _q.total_count
            _quota_last = (_q.reserved_count + _q.booked_count) == 1

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
        # Phase 3
        checkin_status=a.checkin_status,
        checked_in_at=a.checked_in_at,
        no_show_type=a.no_show_type,
        no_show_fee=float(a.no_show_fee or 0),
        fee_item=a.fee_item,
        plan_id=a.plan_id,
        transport_fee=float(a.transport_fee or 0),
        video_link=a.video_link,
        notify_admin_to_forward=a.notify_admin_to_forward,
        forwarded_at=a.forwarded_at,
        outreach_location=a.outreach_location,
        hourly_rate=float(a.hourly_rate) if a.hourly_rate is not None else None,
        is_intake=a.is_intake,
        quota_is_last_session=_quota_last,
        quota_used=_quota_used,
        quota_total=_quota_total,
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
        if not (q.valid_from <= appt_date <= q.valid_until):
            raise HTTPException(status_code=400, detail=f"預約日 {appt_date} 不在 Quota 有效期間 {q.valid_from} ~ {q.valid_until}")
        # Phase 3 起改看三態的 reserved_count（已預留），不再即時數 appointments。
        # 兩者原本可能不一致；三態由 DB CHECK 強制恆等，是唯一真相。
        if q.reserved_count < 1:
            raise HTTPException(
                status_code=400,
                detail=(f"該扣額已無可用次數（已使用 {q.used_count}／已預約 "
                        f"{q.booked_count}／已預留 {q.reserved_count}）"),
            )
        return q.id

    # Auto-pick FIFO by valid_until (also check reserved)
    candidates = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            CaseInstitutionQuota.valid_from <= appt_date,
            CaseInstitutionQuota.valid_until >= appt_date,
            CaseInstitutionQuota.reserved_count > 0,
            CaseInstitutionQuota.status == "active",
        )
        .order_by(CaseInstitutionQuota.valid_until.asc(), CaseInstitutionQuota.id.asc())
        .all()
    )
    # 同時有多個方案時「一個用完才用下一個」，依有效期先到先用
    candidate = candidates[0] if candidates else None
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

    seq = _next_seq(db, therapist.user_code, body.start_time)
    number = _make_number(therapist.user_code, body.start_time, seq)
    visit_seq = _next_visit_seq(db, body.case_id)

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
        time_range=time_range,
        amount=body.amount,
        funding_source=body.funding_source,
        quota_id=quota_id,
        visit_seq=visit_seq,
        couple_case_id=body.couple_case_id,
        status="booked",
        created_by=user.id,
    )
    db.add(appt)
    # 排預約 → 已預留轉已預約
    if quota_id:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
        if q:
            quota_flow.reserve_to_booked(q)
    db.commit()
    db.refresh(appt)
    return _to_response(appt, therapist, db)


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
        amount = slot.amount if slot.amount is not None else body.amount
        slot_funding = slot.funding_source or body.funding_source
        slot_quota = slot.quota_id if slot.quota_id is not None else (
            body.quota_id if slot.funding_source is None else None
        )

        if body.room_id:
            _check_room_conflict(db, body.room_id, slot.start_time, slot.end_time)

        quota_id = _resolve_quota(
            db, body.case_id, slot_funding, slot_quota, slot.start_time.date()
        )

        seq = _next_seq(db, therapist.user_code, slot.start_time)
        number = _make_number(therapist.user_code, slot.start_time, seq)
        time_range = DateTimeTZRange(slot.start_time, slot.end_time)

        appt = Appointment(
            appointment_number=number,
            case_id=body.case_id,
            therapist_id=therapist.id,
            room_id=body.room_id,
            session_type=body.session_type,
            time_range=time_range,
            amount=amount,
            funding_source=slot_funding,
            quota_id=quota_id,
            visit_seq=next_vs + i,
            couple_case_id=body.couple_case_id,
            status="booked",
            batch_id=batch_id,
            created_by=user.id,
        )
        db.add(appt)
        # 批次預約會一次佔用 N 次額度；額度不足時 reserve_to_booked 會擋下並回報
        # 剩餘可建立的筆數，整批 rollback（不會建到一半）
        if quota_id:
            q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
            if q:
                quota_flow.reserve_to_booked(q)
        db.flush()
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
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "therapist" and a.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if a.status != "booked":
        raise HTTPException(status_code=400, detail=f"Cannot cancel appointment with status '{a.status}'")

    today = date.today()
    appt_date = a.time_range.lower.date() if a.time_range else None
    if appt_date and appt_date < today:
        raise HTTPException(status_code=400, detail="Cannot cancel past appointments")

    if a.time_range and a.time_range.upper is not None:
        cutoff = a.time_range.upper - timedelta(minutes=SETTLEMENT_LEAD_MINUTES)
        now = datetime.now(timezone.utc)
        if now >= cutoff:
            cutoff_local = cutoff.astimezone().strftime("%Y-%m-%d %H:%M")
            raise HTTPException(
                status_code=400,
                detail=f"已逾可取消時限（{cutoff_local}），請洽行政協助處理",
            )

    a.status = "cancelled"
    a.checkin_status = "pending"
    # 取消 → 已預約退回已預留
    if a.quota_id:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
        if q:
            quota_flow.booked_to_reserved(q)
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
    sql = """
        SELECT id FROM appointments
        WHERE room_id = :room_id
          AND status != 'cancelled'
          AND time_range && tstzrange(:start, :end)
    """
    params: dict = {"room_id": room_id, "start": start.isoformat(), "end": end.isoformat()}
    if exclude_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_id
    sql += " LIMIT 1"
    conflict = db.execute(text(sql), params).first()
    if conflict:
        raise HTTPException(status_code=409, detail="Room time slot conflict")


# ---------------------------------------------------------------------------
# 報到（Phase 3）
#
# 診間日曆主控台的核心操作。收款與開立收據排在 Phase 4，此處只做報到／未到
# 與額度流轉。
# ---------------------------------------------------------------------------
class CheckInBody(BaseModel):
    """未到時需指定類型，失約費依原型 rooms 定案⑥自動帶入。"""

    no_show_type: str | None = None
    note: str | None = None


# 24 小時前請假 $0／臨時取消 $200／無故未到 $500
NO_SHOW_FEES = {"advance_notice": 0, "late_cancel": 200, "no_notice": 500}


@router.put("/{appointment_id}/arrive", response_model=AppointmentResponse)
def mark_arrived(
    appointment_id: int,
    user: User = Depends(RequireRole(["admin", "staff", "accountant"])),
    db: Session = Depends(get_db),
):
    """初診／一般預約報到「已到」：轉已執行並把額度由已預約轉已使用。"""
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if a.checkin_status == "arrived":
        raise HTTPException(status_code=400, detail="此預約已報到")
    if a.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的預約不可報到")

    a.checkin_status = "arrived"
    a.checked_in_at = datetime.now(timezone.utc)
    a.checked_in_by = user.id
    a.status = "executed"
    if a.quota_id:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
        if q:
            quota_flow.booked_to_used(q)
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"}, {"checkin_status": "arrived"})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.put("/{appointment_id}/absent", response_model=AppointmentResponse)
def mark_absent(
    appointment_id: int,
    body: CheckInBody,
    user: User = Depends(RequireRole(["admin", "staff", "accountant"])),
    db: Session = Depends(get_db),
):
    """報到「未到」：不產生應收諮商費，機構額度釋回為可用，另計失約費。"""
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if a.checkin_status == "arrived":
        raise HTTPException(status_code=400, detail="已報到的預約不可改為未到，請洽管理員")
    if body.no_show_type not in NO_SHOW_FEES:
        raise HTTPException(
            status_code=400,
            detail=f"no_show_type 需為 {list(NO_SHOW_FEES)}",
        )

    a.checkin_status = "absent"
    a.checked_in_at = datetime.now(timezone.utc)
    a.checked_in_by = user.id
    a.status = "no_show"
    a.no_show_type = body.no_show_type
    a.no_show_fee = NO_SHOW_FEES[body.no_show_type]
    if a.quota_id:
        q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
        if q:
            quota_flow.booked_to_reserved(q)
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"},
                {"checkin_status": "absent", "no_show_type": body.no_show_type,
                 "no_show_fee": float(a.no_show_fee)})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)
