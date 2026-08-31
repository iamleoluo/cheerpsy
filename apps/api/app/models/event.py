from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Event(Base):
    """活動／講座／場地借用（5F 雲燈教室）。

    登記與空間佔用的規則明確，已實作。
    **講師費的財務歸屬尚未定案**——「講師費是否入慈恩帳戶」「講座是否酌收
    行政服務費（是→扣除後轉入心理師當月收入；否→從心理師當月收入扣回）」
    要等機構案完整設計。因此下列欄位雖已建立，但**不進入月報表與酬勞計算**。
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False)
    speaker = Column(String(200), nullable=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)

    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    # 場佈時間也會佔用空間
    setup_start_at = Column(DateTime(timezone=True), nullable=True)
    setup_end_at = Column(DateTime(timezone=True), nullable=True)

    borrower_type = Column(String(20), nullable=False)  # therapist / staff / external
    borrower_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    borrower_name = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)

    # ── 講師費：欄位先建，財務歸屬待 Q16／Q17 定案 ──
    has_lecture_fee = Column(Boolean, nullable=False, default=False, server_default="false")
    lecture_hourly_rate = Column(Numeric(10, 2), nullable=True)
    lecture_hours = Column(Numeric(6, 2), nullable=True)
    lecture_total = Column(Numeric(12, 2), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    room = relationship("Room", lazy="joined")
