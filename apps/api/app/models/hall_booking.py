"""5F 雲燈教室借用（06 P6、02 §1.2、v7 預約作業 n4）。

刻意**不掛在 rooms 表底下**：雲燈教室是 5 樓的單一活動空間，不是定稿那
12 間診間之一。掛進 rooms 會讓它出現在診間日曆的欄位、預約表單的下拉、
空間利用率報表裡，那些地方講的都是「晤談用的診間」。行政端看它的方式是
診間日曆的第三個分頁，不是第十三個欄位。

兩段時間：場佈時段與活動時段分開記。場佈通常提早一兩個小時，佔用空間但
不是活動本身，行政要能一眼看出「這段是在搬桌椅」。
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import relationship

from app.database import Base


class HallBooking(Base):
    __tablename__ = "hall_bookings"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    setup_range = Column(TSTZRANGE, nullable=True)   # 場佈時段（選填）
    event_range = Column(TSTZRANGE, nullable=False)  # 活動時段

    lecturer_kind = Column(String(20), nullable=False, default="internal", server_default="internal")
    # internal(所內心理師) | external(外聘講師)
    lecturer_therapist_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    lecturer_name = Column(String(100), nullable=True)  # 外聘時填
    lecturer_fee = Column(Numeric(10, 2), nullable=True)
    # 講師費是否入慈恩帳戶：False = 主辦單位直接付給講師，診所只出場地
    fee_to_clinic_account = Column(Boolean, nullable=False, default=True, server_default="true")

    borrower = Column(String(100), nullable=True)  # 借用單位/人
    attendee_count = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="scheduled", server_default="scheduled")
    # scheduled(已排定) | executed(已執行) | cancelled(已取消)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lecturer_therapist = relationship("User", foreign_keys=[lecturer_therapist_id])
