"""場地租借（06 P6、02 §1.2、v7 預約作業 b4）。

外部單位或心理師個人向診所借診間使用。與一般預約的差別是「沒有個案、
沒有額度、沒有抽成」，但**佔用同一批實體診間**，所以衝突檢查要跟
appointments 一起做（見 app/services/room_occupancy.py）。

兩個維度決定這筆錢怎麼走：

  renter_kind
    institution  外部機構借用 → 場地費進機構應收，跟著核銷走
    private      心理師個人借用 → 從該心理師當月酬勞扣回

  supervision_fee_mode（督導場次專用，其餘留 NULL）
    A  櫃台代收督導費、開立收據，場地費自動 $0（診所收的是督導費）
    B  心理師自收督導費，場地費照收並由酬勞回扣，不開收據

未到（no_show）時付款方改為「借用人自付」——場地已經被佔住了，成本不會
因為人沒來就消失。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import relationship

from app.database import Base


class VenueRental(Base):
    __tablename__ = "venue_rentals"

    id = Column(Integer, primary_key=True)
    rental_no = Column(String(30), unique=True, nullable=False, index=True)  # V{YYYYMMDD}{流水3碼}
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    time_range = Column(TSTZRANGE, nullable=False)

    purpose = Column(String(100), nullable=True)  # 督導、團體、工作坊、會議…
    renter_kind = Column(String(20), nullable=False, default="institution", server_default="institution")
    renter_name = Column(String(100), nullable=False)  # 借用人/單位名稱（顯示用）
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True, index=True)
    renter_therapist_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    supervision_fee_mode = Column(String(1), nullable=True)  # A | B | NULL(非督導場次)
    amount = Column(Numeric(10, 2), nullable=False, default=0)  # 場地費
    payer = Column(String(20), nullable=False, default="renter", server_default="renter")
    # payer: institution(機構應收) | therapist(心理師酬勞扣回) | renter(借用人當場自付)

    attendance = Column(String(20), nullable=False, default="pending", server_default="pending")
    # pending | arrived | no_show —— 未到時 payer 會被改成 renter
    attended_at = Column(DateTime(timezone=True), nullable=True)
    attended_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(String(20), nullable=False, default="booked", server_default="booked")  # booked | cancelled
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room")
    institution = relationship("Institution")
    renter_therapist = relationship("User", foreign_keys=[renter_therapist_id])
