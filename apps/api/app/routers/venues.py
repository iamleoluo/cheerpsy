"""場地租借與 5F 雲燈教室（06 P6、02 §1.2、v7 預約作業 b4/n4）。

兩件事放同一支路由，因為它們是同一類東西：**沒有個案、沒有額度、沒有抽成
的空間佔用**。差別只在場地租借佔用實體診間（要跟一般預約一起做衝突檢查），
雲燈教室是 5 樓獨立空間（自己跟自己不重疊就好）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg2.extras import DateTimeTZRange
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.hall_booking import HallBooking
from app.models.user import User
from app.models.venue_rental import VenueRental
from app.services import numbering, room_occupancy
from app.services.audit import write_audit
from app.utils.tz import to_local_date

router = APIRouter(prefix="/venues", tags=["venues"])

WRITE_ROLES = ["admin", "staff"]
RENTER_KINDS = ("institution", "private")
PAYERS = ("institution", "therapist", "renter")


# ─────────────────────────────────────────────────────────────────────────
# 場地租借
# ─────────────────────────────────────────────────────────────────────────

class RentalCreate(BaseModel):
    room_id: int
    start_time: datetime
    end_time: datetime
    renter_name: str
    renter_kind: str = "institution"
    purpose: str | None = None
    institution_id: int | None = None
    renter_therapist_id: int | None = None
    supervision_fee_mode: str | None = None  # A | B | None
    amount: float = 0
    note: str | None = None


class RentalResponse(BaseModel):
    id: int
    rental_no: str
    room_id: int
    room_name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    purpose: str | None = None
    renter_kind: str
    renter_name: str
    institution_id: int | None = None
    renter_therapist_id: int | None = None
    renter_therapist_name: str | None = None
    supervision_fee_mode: str | None = None
    amount: float
    payer: str
    attendance: str
    status: str
    note: str | None = None
    created_at: datetime | None = None


def _rental_to_response(v: VenueRental) -> RentalResponse:
    return RentalResponse(
        id=v.id, rental_no=v.rental_no, room_id=v.room_id,
        room_name=v.room.name if v.room else None,
        start_time=v.time_range.lower if v.time_range else None,
        end_time=v.time_range.upper if v.time_range else None,
        purpose=v.purpose, renter_kind=v.renter_kind, renter_name=v.renter_name,
        institution_id=v.institution_id, renter_therapist_id=v.renter_therapist_id,
        renter_therapist_name=v.renter_therapist.name if v.renter_therapist else None,
        supervision_fee_mode=v.supervision_fee_mode, amount=float(v.amount or 0),
        payer=v.payer, attendance=v.attendance, status=v.status, note=v.note,
        created_at=v.created_at,
    )


def _resolve_payer(kind: str, mode: str | None) -> tuple[str, Decimal | None]:
    """付款方與場地費的推導規則（v7 預約作業 b4）。

    督導模式 A：櫃台代收督導費、開立收據，**場地費自動 $0**——診所收的是
    督導費，不再另外跟心理師收場地租金，否則等於收兩次。
    督導模式 B：心理師自收督導費，場地費照收，從當月酬勞回扣，不開收據。
    非督導場次：機構借用 → 機構應收；心理師個人借用 → 酬勞扣回。
    """
    if mode == "A":
        return "renter", Decimal("0")
    if mode == "B":
        return "therapist", None
    return ("institution" if kind == "institution" else "therapist"), None


@router.get("", response_model=list[RentalResponse])
def list_rentals(
    start: datetime | None = None,
    end: datetime | None = None,
    room_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(VenueRental).options(joinedload(VenueRental.room),
                                      joinedload(VenueRental.renter_therapist))
    if room_id:
        q = q.filter(VenueRental.room_id == room_id)
    if start and end:
        q = q.filter(text("time_range && :r").bindparams(r=f"[{start.isoformat()},{end.isoformat()})"))
    return [_rental_to_response(v) for v in q.order_by(VenueRental.id.desc()).limit(300).all()]


@router.post("", response_model=RentalResponse, status_code=status.HTTP_201_CREATED)
def create_rental(
    body: RentalCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")
    if body.renter_kind not in RENTER_KINDS:
        raise HTTPException(status_code=400, detail=f"renter_kind 須為 {RENTER_KINDS}")
    if body.supervision_fee_mode not in (None, "A", "B"):
        raise HTTPException(status_code=400, detail="督導收費模式須為 A 或 B")
    if body.renter_kind == "institution" and not body.institution_id:
        raise HTTPException(status_code=400, detail="機構借用需指定機構")
    if body.renter_kind == "private" and not body.renter_therapist_id:
        raise HTTPException(status_code=400, detail="個人借用需指定心理師")

    # 診間是跟一般預約共用的，衝突要一起看（見 services/room_occupancy.py）
    room_occupancy.assert_free(db, body.room_id, body.start_time, body.end_time)

    payer, forced_amount = _resolve_payer(body.renter_kind, body.supervision_fee_mode)
    amount = forced_amount if forced_amount is not None else Decimal(str(body.amount))

    rental = VenueRental(
        rental_no=numbering.next_venue_rental_no(db, on_date=to_local_date(body.start_time)),
        room_id=body.room_id,
        time_range=DateTimeTZRange(body.start_time, body.end_time),
        purpose=body.purpose, renter_kind=body.renter_kind, renter_name=body.renter_name,
        institution_id=body.institution_id if body.renter_kind == "institution" else None,
        renter_therapist_id=body.renter_therapist_id,
        supervision_fee_mode=body.supervision_fee_mode,
        amount=amount, payer=payer, created_by=user.id,
        note=body.note,
    )
    db.add(rental)
    db.flush()
    write_audit(db, "venue_rentals", rental.id, "CREATE", user.id, None,
                {"rental_no": rental.rental_no, "payer": payer, "amount": float(amount)})
    db.commit()
    db.refresh(rental)
    return _rental_to_response(rental)


class RentalAttendanceRequest(BaseModel):
    attendance: str  # arrived | no_show


@router.put("/{rental_id}/attendance", response_model=RentalResponse)
def set_rental_attendance(
    rental_id: int,
    body: RentalAttendanceRequest,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """已到／未到。未到時付款方改為「借用人自付」——場地已經被佔住了，
    成本不會因為人沒來就消失（v7 預約作業 b4 定案）。"""
    if body.attendance not in ("arrived", "no_show"):
        raise HTTPException(status_code=400, detail="attendance 須為 arrived 或 no_show")
    rental = db.query(VenueRental).filter(VenueRental.id == rental_id).first()
    if not rental:
        raise HTTPException(status_code=404, detail="找不到此場地租借")
    if rental.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的租借不能登錄出席")

    before = {"attendance": rental.attendance, "payer": rental.payer}
    rental.attendance = body.attendance
    rental.attended_at = datetime.now(timezone.utc)
    rental.attended_by = user.id
    if body.attendance == "no_show":
        rental.payer = "renter"
    write_audit(db, "venue_rentals", rental.id, "UPDATE", user.id, before,
                {"attendance": rental.attendance, "payer": rental.payer})
    db.commit()
    db.refresh(rental)
    return _rental_to_response(rental)


@router.put("/{rental_id}/cancel", response_model=RentalResponse)
def cancel_rental(
    rental_id: int,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    rental = db.query(VenueRental).filter(VenueRental.id == rental_id).first()
    if not rental:
        raise HTTPException(status_code=404, detail="找不到此場地租借")
    rental.status = "cancelled"
    write_audit(db, "venue_rentals", rental.id, "UPDATE", user.id,
                {"status": "booked"}, {"status": "cancelled"})
    db.commit()
    db.refresh(rental)
    return _rental_to_response(rental)


# ─────────────────────────────────────────────────────────────────────────
# 5F 雲燈教室
# ─────────────────────────────────────────────────────────────────────────

class HallCreate(BaseModel):
    title: str
    event_start: datetime
    event_end: datetime
    setup_start: datetime | None = None
    setup_end: datetime | None = None
    lecturer_kind: str = "internal"
    lecturer_therapist_id: int | None = None
    lecturer_name: str | None = None
    lecturer_fee: float | None = None
    fee_to_clinic_account: bool = True
    borrower: str | None = None
    attendee_count: int | None = None
    note: str | None = None


class HallResponse(BaseModel):
    id: int
    title: str
    setup_start: datetime | None = None
    setup_end: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    lecturer_kind: str
    lecturer_therapist_id: int | None = None
    lecturer_name: str | None = None
    lecturer_fee: float | None = None
    fee_to_clinic_account: bool
    borrower: str | None = None
    attendee_count: int | None = None
    status: str
    note: str | None = None


def _hall_to_response(h: HallBooking) -> HallResponse:
    return HallResponse(
        id=h.id, title=h.title,
        setup_start=h.setup_range.lower if h.setup_range else None,
        setup_end=h.setup_range.upper if h.setup_range else None,
        event_start=h.event_range.lower if h.event_range else None,
        event_end=h.event_range.upper if h.event_range else None,
        lecturer_kind=h.lecturer_kind,
        lecturer_therapist_id=h.lecturer_therapist_id,
        lecturer_name=h.lecturer_name or (h.lecturer_therapist.name if h.lecturer_therapist else None),
        lecturer_fee=float(h.lecturer_fee) if h.lecturer_fee is not None else None,
        fee_to_clinic_account=h.fee_to_clinic_account, borrower=h.borrower,
        attendee_count=h.attendee_count, status=h.status, note=h.note,
    )


@router.get("/hall", response_model=list[HallResponse])
def list_hall_bookings(
    start: datetime | None = None,
    end: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(HallBooking).options(joinedload(HallBooking.lecturer_therapist))
    if start and end:
        q = q.filter(text("event_range && :r").bindparams(r=f"[{start.isoformat()},{end.isoformat()})"))
    return [_hall_to_response(h) for h in q.order_by(HallBooking.id.desc()).limit(200).all()]


@router.post("/hall", response_model=HallResponse, status_code=status.HTTP_201_CREATED)
def create_hall_booking(
    body: HallCreate,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    if body.event_end <= body.event_start:
        raise HTTPException(status_code=400, detail="活動結束時間必須晚於開始時間")
    if body.lecturer_kind not in ("internal", "external"):
        raise HTTPException(status_code=400, detail="lecturer_kind 須為 internal 或 external")
    if body.lecturer_kind == "internal" and not body.lecturer_therapist_id:
        raise HTTPException(status_code=400, detail="所內講師需指定心理師")
    if body.lecturer_kind == "external" and not (body.lecturer_name or "").strip():
        raise HTTPException(status_code=400, detail="外聘講師需填寫姓名")

    setup = None
    if body.setup_start and body.setup_end:
        if body.setup_end > body.event_start:
            raise HTTPException(status_code=400, detail="場佈時段必須在活動開始前結束")
        setup = DateTimeTZRange(body.setup_start, body.setup_end)

    hall = HallBooking(
        title=body.title, setup_range=setup,
        event_range=DateTimeTZRange(body.event_start, body.event_end),
        lecturer_kind=body.lecturer_kind,
        lecturer_therapist_id=body.lecturer_therapist_id if body.lecturer_kind == "internal" else None,
        lecturer_name=body.lecturer_name if body.lecturer_kind == "external" else None,
        lecturer_fee=body.lecturer_fee, fee_to_clinic_account=body.fee_to_clinic_account,
        borrower=body.borrower, attendee_count=body.attendee_count,
        note=body.note, created_by=user.id,
    )
    db.add(hall)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        if "excl_hall_event_overlap" in str(getattr(e, "orig", e)):
            raise HTTPException(status_code=409, detail="雲燈教室該時段已被借用")
        raise
    write_audit(db, "hall_bookings", hall.id, "CREATE", user.id, None, {"title": hall.title})
    db.commit()
    db.refresh(hall)
    return _hall_to_response(hall)


class HallStatusRequest(BaseModel):
    status: str  # executed | cancelled


@router.put("/hall/{booking_id}/status", response_model=HallResponse)
def set_hall_status(
    booking_id: int,
    body: HallStatusRequest,
    user: User = Depends(RequireRole(WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    if body.status not in ("scheduled", "executed", "cancelled"):
        raise HTTPException(status_code=400, detail="status 須為 scheduled / executed / cancelled")
    hall = db.query(HallBooking).filter(HallBooking.id == booking_id).first()
    if not hall:
        raise HTTPException(status_code=404, detail="找不到此借用紀錄")
    before = {"status": hall.status}
    hall.status = body.status
    write_audit(db, "hall_bookings", hall.id, "UPDATE", user.id, before, {"status": hall.status})
    db.commit()
    db.refresh(hall)
    return _hall_to_response(hall)
