import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from psycopg2.extras import DateTimeTZRange
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit
from app.schemas.appointment import (
    AppointmentBatchCreate,
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
)

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
    # 上線 A：回應不再帶任何金額、分潤、額度、失約費、方案資料。
    # 這些欄位在 schema 裡保留為佔位值（amount=0，其餘 null／False），上線 B 才移除。
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


def _to_occupied_response(a: Appointment) -> AppointmentResponse:
    """別的心理師的場次：只露出「已佔用」所需資訊，不含任何個案或金額資料。"""
    start = a.time_range.lower if a.time_range else None
    end = a.time_range.upper if a.time_range else None
    return AppointmentResponse(
        id=a.id,
        appointment_number="",
        case_id=0,
        therapist_id=a.therapist_id,
        therapist_name=a.therapist.name if a.therapist else None,
        room_id=a.room_id,
        room_name=a.room.name if a.room else None,
        session_type="in_person",
        start_time=start,
        end_time=end,
        status=a.status,
        occupied_only=True,
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
        # 心理師：自己的場次完整可見；帶 room_id 時另外看到該診間「別人的有效場次」，
        # 但那些只會以 _to_occupied_response 遮罩回傳。case_id 只能查自己的個案。
        if room_id:
            query = query.filter(
                or_(
                    Appointment.therapist_id == user.id,
                    and_(
                        Appointment.room_id == room_id,
                        Appointment.status.in_(["booked", "executed"]),
                    ),
                )
            )
        else:
            query = query.filter(Appointment.therapist_id == user.id)
        if case_id:
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
        _to_occupied_response(a)
        if user.role == "therapist" and a.therapist_id != user.id
        else _to_response(a, therapists.get(a.therapist_id), db, viewer=user)
        for a in appointments
    ]


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

    time_range = DateTimeTZRange(body.start_time, body.end_time)
    appt = Appointment(
        appointment_number=number,
        case_id=body.case_id,
        therapist_id=therapist.id,
        room_id=body.room_id,
        session_type=body.session_type,
        time_range=time_range,
        amount=0,  # 上線 A：金額由伺服器填 0，忽略前端送來的值
        visit_seq=visit_seq,
        couple_case_id=body.couple_case_id,
        status="booked",
        created_by=user.id,
    )
    db.add(appt)
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
        if body.room_id:
            _check_room_conflict(db, body.room_id, slot.start_time, slot.end_time)

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
            amount=0,  # 上線 A：金額由伺服器填 0
            visit_seq=next_vs + i,
            couple_case_id=body.couple_case_id,
            status="booked",
            batch_id=batch_id,
            created_by=user.id,
        )
        db.add(appt)
        # flush 讓同批次後面的 slot 也能看到前面的佔用（診間衝突檢查）
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
        "time_range": str(a.time_range),
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
    # 上線 A：amount／funding_source／quota_id 已忽略

    after = {
        "room_id": a.room_id, "session_type": a.session_type,
        "time_range": str(a.time_range),
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
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"status": "booked"}, {"status": "cancelled"})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)


@router.put("/{appointment_id}/payment", status_code=status.HTTP_410_GONE)
def update_appointment_payment(user: User = Depends(get_current_user)):
    """帳務拆除上線 A：付款方式與機構額度已停用，不再寫入。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="付款方式功能已停用")


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


@router.put("/{appointment_id}/amount", status_code=status.HTTP_410_GONE)
def update_amount(user: User = Depends(get_current_user)):
    """帳務拆除上線 A：預約金額已停用，伺服器一律寫 0。"""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="預約金額功能已停用")


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
    user: User = Depends(RequireRole(["admin", "staff", "accountant"])),
    db: Session = Depends(get_db),
):
    """初診／一般預約報到「已到」：只轉為已執行，不產生帳務紀錄。"""
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
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"},
                {"checkin_status": "arrived"})
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
    """報到「未到」：只記錄未到類型，不產生帳務紀錄、不計失約費。"""
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")
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
    write_audit(db, "appointments", a.id, "UPDATE", user.id,
                {"checkin_status": "pending"},
                {"checkin_status": "absent", "no_show_type": body.no_show_type})
    db.commit()
    db.refresh(a)
    therapist = db.query(User).filter(User.id == a.therapist_id).first()
    return _to_response(a, therapist, db, viewer=user)
