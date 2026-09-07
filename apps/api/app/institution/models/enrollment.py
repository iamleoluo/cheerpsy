"""Layer 1・個案的機構狀態列表。見 07 §4.1。

一個個案在一個方案下只會有一筆 enrollment（同一人不可重複加入同一方案）。
擁有者是子系統；主系統完全不落地這張表的資料，只透過
funding.ports.get_case_enrollments() 唯讀查詢。

額度三態：
    已預留 reserved_count —— 加入方案當下，quota_limit 全數進這裡
    已預約 —— 不落地，= 指向此 enrollment 且 status='booked' 的 appointments 數量
    已使用 used_count —— 報到已到後累計
恆等式：quota_limit + extended_count = used_count + reserved_count + COUNT(booked)
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class InstEnrollment(Base):
    __tablename__ = "inst_enrollments"
    __table_args__ = (UniqueConstraint("case_id", "plan_id", name="uq_enrollment_case_plan"),)

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("inst_plans.id"), nullable=False, index=True)

    # 機構端配發的個案代號。16 個方案需要（見 07 §1.6）。
    # 依 08 決策：流水號階段（未初診）可以 enroll/reserve，但要 consume（真正產生
    # 金流）必須先有正式病歷號；requires_external_code=true 的方案若代號仍是
    # NULL，consume() 仍放行但標記待補，核銷收納時才擋（見 07 §8.3）。
    external_case_code = Column(String(50), nullable=True)

    quota_unit = Column(String(10), nullable=False, default="count", server_default="count")
    quota_limit = Column(Numeric(10, 2), nullable=True)  # NULL = 不限
    reserved_count = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    used_count = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")

    # 經評估延長的額度（警局 6+3、奇美家照 6+3，見 07 §1.2）
    extended_count = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    extension_approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    extension_approved_at = Column(DateTime(timezone=True), nullable=True)
    extension_note = Column(Text, nullable=True)

    # 週期性子上限（容愛協會：每月4次、累計24次）——由 plan 帶入預設值，此處可個案覆寫
    period_limit = Column(Integer, nullable=True)
    period_unit = Column(String(10), nullable=True)

    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)

    assessment_status = Column(String(20), nullable=False, default="not_required", server_default="not_required")
    status = Column(String(20), nullable=False, default="active", server_default="active")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", lazy="joined")
    plan = relationship("InstPlan", lazy="joined")
