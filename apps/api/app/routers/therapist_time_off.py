"""心理師「這段不接案」。

- 心理師管自己的（新增、看、刪）；admin／staff 管全部。別人的一律 404（與不存在相同）。
- 原因（reason）只有本人與 admin／staff 看得到；/blocked 給預約畫面畫灰格，永遠不含原因。
- 預約落在這段時間會被擋下（409，見 slot_check.assert_therapist_available）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import DateTimeTZRange
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.therapist_time_off import TherapistTimeOff
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/therapist-time-off", tags=["therapist-time-off"])
ROLES = ["admin", "staff", "therapist"]


class TimeOffIn(BaseModel):
    start_time: datetime
    end_time: datetime
    reason: str | None = None
    therapist_id: int | None = None  # 心理師可省略（＝自己）；行政必填


class TimeOffOut(BaseModel):
    id: int
    therapist_id: int
    start_time: datetime
    end_time: datetime
    reason: str | None = None
    overlapping_appointments: int = 0  # 新增當下已落在這段的 booked 預約數（只提醒，不取消）


class BlockedOut(BaseModel):
    therapist_id: int
    start_time: datetime
    end_time: datetime


def _out(r: TherapistTimeOff, overlapping: int = 0) -> TimeOffOut:
    return TimeOffOut(id=r.id, therapist_id=r.therapist_id, start_time=r.time_range.lower,
                      end_time=r.time_range.upper, reason=r.reason, overlapping_appointments=overlapping)


def _scope_therapist(user: User, therapist_id: int | None) -> int | None:
    """心理師只能看自己；指定別人一律 404。行政不指定＝全部。"""
    if user.role == "therapist":
        if therapist_id is not None and therapist_id != user.id:
            raise HTTPException(status_code=404, detail="Not found")
        return user.id
    return therapist_id


def _rows(db: Session, therapist_id: int | None, start: datetime | None, end: datetime | None):
    q = db.query(TherapistTimeOff)
    if therapist_id is not None:
        q = q.filter(TherapistTimeOff.therapist_id == therapist_id)
    if start is not None and end is not None:
        q = q.filter(TherapistTimeOff.time_range.op("&&")(func.tstzrange(start, end)))
    return q.order_by(TherapistTimeOff.id).all()


@router.get("", response_model=list[TimeOffOut])
def list_time_off(
    therapist_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    tid = _scope_therapist(user, therapist_id)
    return [_out(r) for r in _rows(db, tid, start, end)]


@router.get("/blocked", response_model=list[BlockedOut])
def blocked(
    therapist_id: int,
    start: datetime,
    end: datetime,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    """預約畫面的灰格：該心理師不可約的時段。不含原因。心理師只能查自己。"""
    tid = _scope_therapist(user, therapist_id)
    return [BlockedOut(therapist_id=r.therapist_id, start_time=r.time_range.lower, end_time=r.time_range.upper)
            for r in _rows(db, tid, start, end)]


@router.post("", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED)
def create_time_off(
    body: TimeOffIn,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=422, detail="結束時間必須晚於開始時間")
    if user.role == "therapist":
        if body.therapist_id not in (None, user.id):
            raise HTTPException(status_code=404, detail="Not found")
        tid = user.id
    else:
        if body.therapist_id is None:
            raise HTTPException(status_code=422, detail="請指定心理師")
        tid = body.therapist_id
        if not db.query(User).filter(User.id == tid, User.role == "therapist").first():
            raise HTTPException(status_code=404, detail="Not found")
    row = TherapistTimeOff(therapist_id=tid, time_range=DateTimeTZRange(body.start_time, body.end_time),
                           reason=(body.reason or "").strip() or None, created_by=user.id)
    db.add(row)
    db.flush()
    overlapping = db.execute(
        text("SELECT count(*) FROM appointments WHERE therapist_id = :t AND status = 'booked' "
             "AND time_range && tstzrange(:s, :e)"),
        {"t": tid, "s": body.start_time, "e": body.end_time}).scalar() or 0
    write_audit(db, "therapist_time_off", row.id, "INSERT", user.id, None,
                {"therapist_id": tid, "start": body.start_time.isoformat(), "end": body.end_time.isoformat()})
    db.commit()
    db.refresh(row)
    return _out(row, int(overlapping))


@router.delete("/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_off(
    time_off_id: int,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    row = db.query(TherapistTimeOff).filter(TherapistTimeOff.id == time_off_id).first()
    if not row or (user.role == "therapist" and row.therapist_id != user.id):
        raise HTTPException(status_code=404, detail="Not found")  # 別人的與不存在相同
    write_audit(db, "therapist_time_off", row.id, "DELETE", user.id, {"therapist_id": row.therapist_id}, None)
    db.delete(row)
    db.commit()
