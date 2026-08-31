from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class CoupleMember(Base):
    """一案連多位個案的成員連結。

    Phase 1b 起實表名為 case_members（伴侶諮商與會面交往同構）。
    舊表名 couple_members 保留為相容 view，既有 query 不會斷。
    類別名暫留 CoupleMember，待引用處收斂後再更名。
    """

    __tablename__ = "case_members"
    __table_args__ = (
        UniqueConstraint("couple_case_id", "member_case_id", name="uq_couple_member"),
    )

    id = Column(Integer, primary_key=True)
    couple_case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    member_case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    # 案主 / 配偶 / 相對人（會面交往）/ 團體成員
    role = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    couple_case = relationship("Case", foreign_keys=[couple_case_id])
    member_case = relationship("Case", foreign_keys=[member_case_id])
