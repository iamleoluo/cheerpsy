from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.event import Event
from app.models.room import Room
from app.models.user import User
from app.schemas.appointment import RoomResponse
from app.services.audit import write_audit
from app.services.slot_check import find_room_conflict

router = APIRouter(prefix="/rooms", tags=["rooms"])

ROOM_ORDER = (Room.sort_order, Room.floor, Room.room_code)
MAX_OCCUPANCY_DAYS = 62


# ---------------------------------------------------------------------------
# 讀取
# ---------------------------------------------------------------------------
@router.get("", response_model=list[RoomResponse])
def list_rooms(
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """預設只回啟用中的診間（給選擇器用）。
    include_inactive=true 會一併回停用的診間：日曆要用它顯示歷史預約，管理畫面要用它維護。"""
    q = db.query(Room)
    if not include_inactive:
        q = q.filter(Room.is_active.is_(True))
    return q.order_by(*ROOM_ORDER).all()


@router.get("/availability", response_model=list[RoomResponse])
def available_rooms(
    start: datetime,
    end: datetime,
    prefer: str | None = Query(None, pattern="^(talk|play)$"),
    exclude_appointment_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """該時段「空著」的診間（沒有 booked／executed 預約，也沒有活動含場佈；停用的診間不列）。

    只回診間本身，不含任何佔用者資訊，所以所有登入角色都可以用。
    prefer 指定的類型排前面（遊戲治療用 play，一般晤談用 talk）；不自動配房，由行政點選。
    改期時帶 exclude_appointment_id，避免把自己原本的時段算成衝突。
    """
    if end <= start:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")
    rooms = db.query(Room).filter(Room.is_active.is_(True)).order_by(*ROOM_ORDER).all()
    free = [
        r for r in rooms
        if find_room_conflict(db, r.id, start, end, exclude_appointment_id=exclude_appointment_id) is None
    ]
    if prefer:
        free.sort(key=lambda r: 0 if r.room_type == prefer else 1)  # 穩定排序，其餘維持原順序
    return free


class OccupancySlot(BaseModel):
    """某診間的一段「已佔用」時段。刻意只有這四個欄位：不含個案、心理師、活動或預約的任何資訊。"""

    room_id: int
    start: datetime
    end: datetime
    occupied: Literal[True] = True


@router.get("/occupancy", response_model=list[OccupancySlot])
def room_occupancy(
    start: datetime,
    end: datetime,
    room_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """各診間在 [start, end) 內被佔用的時段。所有登入角色都能用，回應不分角色、不含個人資料。

    佔用 = booked／executed 的預約，加上活動（含場佈時間）。cancelled、no_show 已釋出，不算。
    不受 /appointments 的 200 筆上限影響；範圍最多 62 天。
    """
    if end <= start:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")
    if end - start > timedelta(days=MAX_OCCUPANCY_DAYS):
        raise HTTPException(status_code=400, detail=f"查詢範圍最多 {MAX_OCCUPANCY_DAYS} 天")

    room_filter = " AND room_id = :room_id" if room_id else ""
    params: dict = {"s": start, "e": end}
    if room_id:
        params["room_id"] = room_id

    rows = db.execute(text(f"""
        SELECT room_id, lower(time_range) AS s, upper(time_range) AS e
        FROM appointments
        WHERE room_id IS NOT NULL AND status IN ('booked', 'executed')
          AND time_range && tstzrange(:s, :e){room_filter}
        UNION ALL
        SELECT room_id, COALESCE(setup_start_at, start_at) AS s, end_at AS e
        FROM events
        WHERE room_id IS NOT NULL
          AND tstzrange(COALESCE(setup_start_at, start_at), end_at) && tstzrange(:s, :e){room_filter}
        ORDER BY room_id, s
    """), params).fetchall()
    return [OccupancySlot(room_id=r.room_id, start=r.s, end=r.e) for r in rows]


# ---------------------------------------------------------------------------
# 診間維護（只有系統管理員；不提供刪除，停用 = is_active=false）
# ---------------------------------------------------------------------------
class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    floor: int
    room_code: str = Field(min_length=1, max_length=20)
    room_type: Literal["talk", "play"] = "talk"
    has_special_equipment: bool = False
    notes: str | None = None
    sort_order: int = 0
    is_active: bool = True


class RoomUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    floor: int | None = None
    room_code: str | None = Field(None, min_length=1, max_length=20)
    room_type: Literal["talk", "play"] | None = None
    has_special_equipment: bool | None = None
    notes: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


def _snapshot(r: Room) -> dict:
    return {
        "name": r.name, "floor": r.floor, "room_code": r.room_code, "room_type": r.room_type,
        "has_special_equipment": r.has_special_equipment, "notes": r.notes,
        "is_active": r.is_active, "sort_order": r.sort_order,
    }


def _dup_code(code: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"診間代號 {code} 已存在")


@router.post("", response_model=RoomResponse, status_code=201)
def create_room(
    body: RoomCreate,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    code = body.room_code.strip()
    if db.query(Room.id).filter(Room.room_code == code).first():
        raise _dup_code(code)
    room = Room(
        name=body.name.strip(), floor=body.floor, room_code=code, room_type=body.room_type,
        has_special_equipment=body.has_special_equipment, notes=body.notes,
        sort_order=body.sort_order, is_active=body.is_active,
    )
    db.add(room)
    try:
        db.flush()
    except IntegrityError:  # 並行建立同一個代號
        db.rollback()
        raise _dup_code(code)
    write_audit(db, "rooms", room.id, "CREATE", user.id, None, _snapshot(room))
    db.commit()
    db.refresh(room)
    return room


@router.put("/{room_id}", response_model=RoomResponse)
def update_room(
    room_id: int,
    body: RoomUpdate,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="診間不存在")
    data = body.model_dump(exclude_unset=True)
    before = _snapshot(room)

    # 停用：還有 booked 預約的診間不能停用（歷史的 executed／cancelled／no_show 不擋）
    if data.get("is_active") is False and room.is_active:
        booked = (
            db.query(func.count(Appointment.id))
            .filter(Appointment.room_id == room.id, Appointment.status == "booked")
            .scalar() or 0
        )
        if booked:
            raise HTTPException(
                status_code=409,
                detail=f"診間 {room.room_code} 還有 {booked} 筆已預約（booked）的場次，請先改期或取消後再停用",
            )

    if "room_code" in data:
        code = (data["room_code"] or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="診間代號不可為空")
        if db.query(Room.id).filter(Room.room_code == code, Room.id != room.id).first():
            raise _dup_code(code)
        data["room_code"] = code
    if "name" in data:
        data["name"] = (data["name"] or "").strip()
        if not data["name"]:
            raise HTTPException(status_code=400, detail="診間名稱不可為空")
    for k in ("is_active", "sort_order", "floor", "room_type", "has_special_equipment"):
        if k in data and data[k] is None:
            data.pop(k)  # 這些欄位不可為 null；None 視為沒送

    for k, v in data.items():
        setattr(room, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _dup_code(data.get("room_code", room.room_code))
    write_audit(db, "rooms", room.id, "UPDATE", user.id, before, _snapshot(room))
    db.commit()
    db.refresh(room)
    return room
