from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class QuotaTemplate(Base):
    __tablename__ = "quota_templates"

    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    total_count = Column(Integer, nullable=False)
    notes = Column(String(500), nullable=True)
    # 預設有效期間：套用範本時帶入，仍可在套用 Modal 編輯
    default_valid_from = Column(Date, nullable=True)
    default_valid_until = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    institution = relationship("Institution", lazy="joined")
    creator = relationship("User", lazy="joined")
