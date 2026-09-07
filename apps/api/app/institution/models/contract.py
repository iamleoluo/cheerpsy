"""合約：簽約單位、窗口、合約期間、對象條件。

一個單位可能簽多份合約（例：衛生局有市民案合約，也有人事處案合約）。
見 V2升級計畫 07_機構合約子系統架構.html §6.1。
"""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstContract(Base):
    __tablename__ = "inst_contracts"

    id = Column(Integer, primary_key=True)
    # 沿用主系統既有的 institutions 表（簽約單位主檔），不重建一套單位清單。
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 合約/計畫名稱，如「國軍心理照護方案」
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_note = Column(Text, nullable=True)
    eligibility_note = Column(Text, nullable=True)  # 方案身份條件（自由文字，如「15-45歲民眾」）
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    institution = relationship("Institution", lazy="joined")
    plans = relationship("InstPlan", back_populates="contract")
