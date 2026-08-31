from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base

# 心智圖 §一.4：上午 0800-1200／下午 1300-1700／晚上 1800-2100
PERIODS = {"morning": "上午 08-12", "afternoon": "下午 13-17", "evening": "晚上 18-21"}


class TherapistAvailability(Base):
    """心理師每週可當診時段。

    用途：行政媒合時可先看誰有空，減少來回；也可看出哪些時段可釋出。
    """

    __tablename__ = "therapist_availability"
    __table_args__ = (
        UniqueConstraint("therapist_id", "weekday", "period", name="uq_therapist_availability"),
    )

    id = Column(Integer, primary_key=True)
    therapist_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)  # 0=週一 … 6=週日
    period = Column(String(20), nullable=False)
