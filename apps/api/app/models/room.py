from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    floor = Column(Integer, nullable=False)
    room_code = Column(String(20), unique=True, nullable=False)
    has_special_equipment = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    # P0（V2升級計畫 02 §1.1）：定稿要求的診間卡標籤（⭐上次使用／👶遊戲室／大間）
    # 需要這兩個屬性才排得出來。use_type: general(晤談室) | play(兒童遊戲室)。
    # size: normal | large。診間主檔本身也要從 13 間測試資料重建為定稿的 12 間，
    # 見 seed.py 的 rebuild_room_roster()。
    use_type = Column(String(20), nullable=False, default="general", server_default="general")
    size = Column(String(20), nullable=False, default="normal", server_default="normal")
