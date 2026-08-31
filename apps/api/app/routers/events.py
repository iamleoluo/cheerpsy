"""活動／講座／場地借用（5F 雲燈教室），以及心理師班表的 iCal 訂閱。

活動的登記與空間佔用已完整實作。講師費的**財務歸屬**尚未定案
（是否入慈恩帳戶、是否酌收行政服務費），故 lecture_* 欄位可以填寫與顯示，
但**不進入月報表與心理師酬勞計算**。
"""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, model_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.event import Event
from app.models.room import Room
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(tags=["events"])

STAFF = ["admin", "accountant", "staff"]
BORROWER_TYPES = {"therapist": "心理師", "staff": "行政", "external": "外部講師"}


class EventIn(BaseModel):
    name: str
    speaker: str | None = None
    room_id: int | None = None
    start_at: datetime
    end_at: datetime
    setup_start_at: datetime | None = None
    setup_end_at: datetime | None = None
    borrower_type: str
    borrower_user_id: int | None = None
    borrower_name: str | None = None
    note: str | None = None
    has_lecture_fee: bool = False
    lecture_hourly_rate: float | None = None
    lecture_hours: float | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.borrower_type not in BORROWER_TYPES:
            raise ValueError(f"borrower_type 需為 {list(BORROWER_TYPES)}")
        if self.end_at <= self.start_at:
            raise ValueError("結束時間需晚於開始時間")
        if (self.setup_start_at is None) != (self.setup_end_at is None):
            raise ValueError("場佈起訖需成對填寫")
        if self.setup_start_at and self.setup_end_at:
            if self.setup_end_at <= self.setup_start_at:
                raise ValueError("場佈結束需晚於場佈開始")
            if self.setup_end_at > self.start_at:
                raise ValueError("場佈需在活動開始前結束")
        if self.borrower_type == "external" and not (self.borrower_name or "").strip():
            raise ValueError("外部講師需填寫借用人姓名")
        if self.borrower_type != "external" and not self.borrower_user_id:
            raise ValueError("內部借用需指定人員")
        if self.has_lecture_fee and (self.lecture_hourly_rate is None or self.lecture_hours is None):
            raise ValueError("勾選有講師費時需填寫鐘點費與時數")
        return self


def _occupied_range(e: Event | EventIn) -> tuple[datetime, datetime]:
    """活動實際佔用空間的區間＝場佈開始 ~ 活動結束。"""
    start = e.setup_start_at or e.start_at
    return start, e.end_at


def _out(e: Event, db: Session) -> dict:
    borrower = (
        db.query(User).filter(User.id == e.borrower_user_id).first()
        if e.borrower_user_id else None
    )
    return {
        "id": e.id,
        "name": e.name,
        "speaker": e.speaker,
        "room_id": e.room_id,
        "room_name": e.room.name if e.room else None,
        "start_at": e.start_at,
        "end_at": e.end_at,
        "setup_start_at": e.setup_start_at,
        "setup_end_at": e.setup_end_at,
        "borrower_type": e.borrower_type,
        "borrower_type_label": BORROWER_TYPES.get(e.borrower_type, e.borrower_type),
        "borrower_name": borrower.name if borrower else e.borrower_name,
        "note": e.note,
        "has_lecture_fee": e.has_lecture_fee,
        "lecture_hourly_rate": float(e.lecture_hourly_rate) if e.lecture_hourly_rate is not None else None,
        "lecture_hours": float(e.lecture_hours) if e.lecture_hours is not None else None,
        "lecture_total": float(e.lecture_total) if e.lecture_total is not None else None,
    }


def _check_conflict(db: Session, body: EventIn, exclude_id: int | None = None) -> None:
    """活動與預約共用同一批空間，兩邊都要檢查。"""
    if not body.room_id:
        return
    if not db.query(Room).filter(Room.id == body.room_id).first():
        raise HTTPException(status_code=404, detail="診間不存在")

    occ_start, occ_end = _occupied_range(body)
    rng = func.tstzrange(occ_start, occ_end)

    appt = (
        db.query(Appointment)
        .filter(
            Appointment.room_id == body.room_id,
            Appointment.status.in_(["booked", "executed"]),
            Appointment.time_range.op("&&")(rng),
        )
        .first()
    )
    if appt:
        raise HTTPException(status_code=409, detail="該空間此時段已有預約（含場佈時間）")

    q = db.query(Event).filter(
        Event.room_id == body.room_id,
        func.tstzrange(func.coalesce(Event.setup_start_at, Event.start_at), Event.end_at).op("&&")(rng),
    )
    if exclude_id:
        q = q.filter(Event.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail="該空間此時段已有其他活動（含場佈時間）")


@router.get("/events")
def list_events(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if start:
        q = q.filter(Event.end_at >= start)
    if end:
        q = q.filter(Event.start_at <= end)
    return [_out(e, db) for e in q.order_by(Event.start_at).all()]


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    _check_conflict(db, body)
    total = (
        round(float(body.lecture_hourly_rate) * float(body.lecture_hours), 2)
        if body.has_lecture_fee else None
    )
    e = Event(
        name=body.name.strip(),
        speaker=body.speaker,
        room_id=body.room_id,
        start_at=body.start_at,
        end_at=body.end_at,
        setup_start_at=body.setup_start_at,
        setup_end_at=body.setup_end_at,
        borrower_type=body.borrower_type,
        borrower_user_id=body.borrower_user_id,
        borrower_name=body.borrower_name,
        note=body.note,
        has_lecture_fee=body.has_lecture_fee,
        lecture_hourly_rate=body.lecture_hourly_rate,
        lecture_hours=body.lecture_hours,
        lecture_total=total,
        created_by=user.id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    write_audit(db, "events", e.id, "INSERT", user.id, None, {"name": e.name})
    db.commit()
    return _out(e, db)


@router.put("/events/{event_id}")
def update_event(
    event_id: int,
    body: EventIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    e = db.query(Event).filter(Event.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    _check_conflict(db, body, exclude_id=event_id)
    for f in ("name", "speaker", "room_id", "start_at", "end_at", "setup_start_at",
              "setup_end_at", "borrower_type", "borrower_user_id", "borrower_name",
              "note", "has_lecture_fee", "lecture_hourly_rate", "lecture_hours"):
        setattr(e, f, getattr(body, f))
    e.lecture_total = (
        round(float(body.lecture_hourly_rate) * float(body.lecture_hours), 2)
        if body.has_lecture_fee else None
    )
    write_audit(db, "events", e.id, "UPDATE", user.id, None, {"name": e.name})
    db.commit()
    db.refresh(e)
    return _out(e, db)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    e = db.query(Event).filter(Event.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    write_audit(db, "events", e.id, "DELETE", user.id, {"name": e.name}, None)
    db.delete(e)
    db.commit()


# ---------------------------------------------------------------------------
# iCal 訂閱：把班表單向匯出到 Google 日曆
#
# 雙向同步需要 Google OAuth client credentials 與授權流程，屬獨立專案。
# 這裡先提供訂閱 feed —— 心理師把 URL 貼進 Google 日曆的「以網址新增日曆」
# 即可看到自己的班表，不需要任何授權設定。
# ---------------------------------------------------------------------------
def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@router.post("/me/ical-token")
def issue_ical_token(
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    """產生（或重新產生）個人訂閱網址。重新產生會使舊網址失效。"""
    user.ical_token = secrets.token_urlsafe(32)[:64]
    db.commit()
    return {
        "token": user.ical_token,
        "path": f"/calendar/{user.ical_token}.ics",
        "note": "把完整網址貼進 Google 日曆的「以網址新增日曆」。重新產生會讓舊網址失效。",
    }


@router.get("/calendar/{token}.ics")
def ical_feed(token: str, db: Session = Depends(get_db)):
    """公開端點：以不可猜測的 token 授權，不需登入。

    只輸出該心理師自己的預約，且**不含個案姓名以外的敏感資訊**
    （不含金額、方案、聯絡方式）。
    """
    u = db.query(User).filter(User.ical_token == token).first()
    if not u:
        raise HTTPException(status_code=404, detail="Not found")

    appts = (
        db.query(Appointment)
        .filter(
            Appointment.therapist_id == u.id,
            Appointment.status.in_(["booked", "executed"]),
        )
        .order_by(Appointment.id)
        .all()
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CheerPsy//Schedule//TW",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(u.name)} 的班表",
    ]
    for a in appts:
        if not a.time_range:
            continue
        case_name = a.case.name if a.case else "（初診）"
        room = a.room.room_code if a.room else ""
        lines += [
            "BEGIN:VEVENT",
            f"UID:cheerpsy-appt-{a.id}@cheerpsy",
            f"DTSTAMP:{_ics_dt(datetime.now(timezone.utc))}",
            f"DTSTART:{_ics_dt(a.time_range.lower)}",
            f"DTEND:{_ics_dt(a.time_range.upper)}",
            f"SUMMARY:{_ics_escape(case_name)}",
            f"LOCATION:{_ics_escape(room)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    return Response(
        content="\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )
