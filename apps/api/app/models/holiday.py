from sqlalchemy import Column, Date, Integer, String

from app.database import Base


class Holiday(Base):
    """國定假日。批次預約時標示提醒，但**不自動跳過**（原型 booking 定案②）。"""

    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True)
    holiday_date = Column(Date, unique=True, nullable=False)
    name = Column(String(100), nullable=False)
