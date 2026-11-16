from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import TSTZRANGE

from app.database import Base


class TherapistTimeOff(Base):
    """心理師「這段不接案」：落在這段時間的預約會被擋下（409）。reason 只有本人與行政看得到。"""

    __tablename__ = "therapist_time_off"

    id = Column(Integer, primary_key=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    time_range = Column(TSTZRANGE, nullable=False)
    reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
