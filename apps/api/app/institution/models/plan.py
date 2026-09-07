"""方案：對外的方案名稱、收據名目、薪酬模式。心理師在預約時挑的就是這個。

一個合約底下可以拆多個方案（例：國軍拆成「國軍-個別」「國軍-講座」
「國軍-本島團輔」三個方案，因為額度要分開給心理師看），但共用同一個
額度池（quota_pool_id）與核銷群組（claim_group_key）。見 07 §6.1。
"""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstPlan(Base):
    __tablename__ = "inst_plans"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("inst_contracts.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 如「衛生局市民」「國軍-個別」
    quota_pool_id = Column(Integer, ForeignKey("inst_quota_pools.id"), nullable=True, index=True)

    # 額度（個案層級，見 07 §4.1）。quota_unit: count | amount。NULL = 不限。
    quota_unit = Column(String(10), nullable=False, default="count", server_default="count")
    default_quota_limit = Column(String(30), nullable=True)  # 存字串以容納 "6+3"/"需評估" 這類原始描述
    default_quota_limit_numeric = Column(Integer, nullable=True)  # 系統實際使用的數字上限，NULL=不限/需評估
    period_limit = Column(Integer, nullable=True)  # 週期性子上限（容愛協會：每月4次）
    period_unit = Column(String(10), nullable=True)  # month / week
    requires_assessment = Column(Boolean, default=False, nullable=False, server_default="false")
    counts_toward_quota = Column(Boolean, default=True, nullable=False, server_default="true")
    # 個案代號需求（16 個方案標記「有」，見 07 §1.6）。
    requires_external_code = Column(Boolean, default=False, nullable=False, server_default="false")

    # 薪酬模式：commission(抽成) / kickback(回扣) / none(無心理師勞務，如借場地)
    compensation_mode = Column(String(12), nullable=False, default="commission", server_default="commission")

    # 收據
    case_receipt_required = Column(Boolean, default=True, nullable=False, server_default="true")
    case_receipt_item_name = Column(String(50), nullable=True)  # 場地費 / 行政規費...
    institution_receipt_required = Column(Boolean, default=False, nullable=False, server_default="false")
    institution_receipt_item_name = Column(String(50), nullable=True)  # 諮商鐘點費...

    # 核銷路由（見 07 §4.3、§6.1；容器本身在 InstClaimCase，這裡只存「怎麼分組、多久收一次」）
    claim_group_key = Column(String(100), nullable=True, index=True)  # 同 group 的方案一起核銷
    claim_timing = Column(String(12), nullable=False, default="monthly", server_default="monthly")
    claim_deadline_day = Column(Integer, nullable=True)
    claim_grouping_mode = Column(String(20), nullable=False, default="period", server_default="period")
    claim_capacity = Column(Integer, nullable=True)  # grouping_mode=per_case_count 時的容器容量
    registered_hours_rule = Column(String(200), nullable=True)  # 自由文字備忘，如「1hr實際→2hr@$800登記」

    # 行政流程提醒清單（54 個方案全部都有，見 07 §1.6）。先用 JSON 字串陣列存，
    # 之後若要逐項勾選狀態的細顆粒度管理，可再拆成獨立表。
    admin_checklist = Column(Text, nullable=True)  # JSON: ["台南市民同意書(第一次)", ...]
    therapist_checklist = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("InstContract", back_populates="plans")
    quota_pool = relationship("InstQuotaPool", back_populates="plans")
    rate_rules = relationship(
        "InstRateRule", back_populates="plan", order_by="InstRateRule.sort_order", cascade="all, delete-orphan"
    )
