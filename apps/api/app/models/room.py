from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    floor = Column(Integer, nullable=False)
    room_code = Column(String(20), unique=True, nullable=False)
    # talk 晤談室／play 兒童遊戲室（僅 2C、2E）
    room_type = Column(String(20), nullable=False, default="talk", server_default="talk")
    has_special_equipment = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    # 停用後不再出現在選擇器、不能新增預約；歷史預約仍照常顯示。不提供刪除。
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
