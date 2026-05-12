from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.room import Room
from app.models.user import User
from app.schemas.appointment import RoomResponse

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomResponse])
def list_rooms(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rooms = db.query(Room).order_by(Room.floor, Room.room_code).all()
    return rooms
