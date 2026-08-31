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
    # 新的三層結構：扣打掛在「方案」上。institution_id 暫留作為過渡與相容欄位，
    # Phase 1b 前端全部改讀 plan 後再收斂。見 gap_analysis.md §1.4
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="SET NULL"), nullable=True, index=True)
    total_count = Column(Integer, nullable=False)
    # 額度三態，恆等式：used + booked + reserved = total_count
    #   reserved 已預留：加入方案時先全數預留，避免額度被別人用光
    #   booked   已預約：已排定但尚未執行
    #   used     已使用：已報到執行完畢，進入核銷流程
    used_count = Column(Integer, nullable=False, default=0, server_default="0")
    booked_count = Column(Integer, nullable=False, default=0, server_default="0")
    reserved_count = Column(Integer, nullable=False, default=0, server_default="0")
    # active（使用中）/ exhausted（已用罄）/ closed（已結案）/ archived（封存）
    status = Column(String(20), nullable=False, default="active", server_default="active")
    # valid_from / valid_until 為 None 表「無時間上限」
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    case = relationship("Case", lazy="joined")
    institution = relationship("Institution", lazy="joined")
    plan = relationship("InstitutionPlan", lazy="joined")
