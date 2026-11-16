from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.room import Room
from app.models.user import User
from app.schemas.appointment import RoomResponse
from app.services.slot_check import find_room_conflict

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomResponse])
def list_rooms(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rooms = db.query(Room).order_by(Room.floor, Room.room_code).all()
    return rooms


@router.get("/availability", response_model=list[RoomResponse])
def available_rooms(
    start: datetime,
    end: datetime,
    prefer: str | None = Query(None, pattern="^(talk|play)$"),
    exclude_appointment_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """該時段「空著」的診間（沒有 booked／executed 預約，也沒有活動含場佈）。

    只回診間本身，不含任何佔用者資訊，所以所有登入角色都可以用。
    prefer 指定的類型排前面（遊戲治療用 play，一般晤談用 talk）；不自動配房，由行政點選。
    改期時帶 exclude_appointment_id，避免把自己原本的時段算成衝突。
    """
    if end <= start:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")
    rooms = db.query(Room).order_by(Room.floor, Room.room_code).all()
    free = [
        r for r in rooms
        if find_room_conflict(db, r.id, start, end, exclude_appointment_id=exclude_appointment_id) is None
    ]
    if prefer:
        free.sort(key=lambda r: 0 if r.room_type == prefer else 1)  # 穩定排序，其餘維持樓層順序
    return free
