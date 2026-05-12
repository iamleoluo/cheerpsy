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
