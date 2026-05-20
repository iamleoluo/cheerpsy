from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class CaseInstitutionQuota(Base):
    __tablename__ = "case_institution_quotas"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    total_count = Column(Integer, nullable=False)
    used_count = Column(Integer, nullable=False, default=0, server_default="0")
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    case = relationship("Case", lazy="joined")
    institution = relationship("Institution", lazy="joined")
