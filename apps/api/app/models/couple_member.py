from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class CoupleMember(Base):
    __tablename__ = "couple_members"
    __table_args__ = (
        UniqueConstraint("couple_case_id", "member_case_id", name="uq_couple_member"),
    )

    id = Column(Integer, primary_key=True)
    couple_case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    member_case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    role = Column(String(20), nullable=True)  # 可選：案主 / 配偶
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    couple_case = relationship("Case", foreign_keys=[couple_case_id])
    member_case = relationship("Case", foreign_keys=[member_case_id])
