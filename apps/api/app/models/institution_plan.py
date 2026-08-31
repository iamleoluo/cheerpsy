from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstitutionPlan(Base):
    """機構方案（由合約開出的年度方案）。

    個案的機構扣打 case_institution_quotas 掛在這一層。
    per_person_count / annual_total_count 為 NULL 代表「不限」。
    見 document_reference/gap_analysis.md §1.1 #6。
    """

    __tablename__ = "institution_plans"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("institution_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 公告方案名

    # 核銷窗口（與合約承辦人可能不同）
    claim_unit = Column(String(200), nullable=True)
    claim_contact = Column(String(100), nullable=True)
    claim_phone = Column(String(50), nullable=True)

    # NULL = 不限
    per_person_count = Column(Integer, nullable=True)
    annual_total_count = Column(Integer, nullable=True)

    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    notes = Column(String(1000), nullable=True)

    # active（使用中）/ exhausted（已用罄）/ expired（已過期）
    status = Column(String(20), nullable=False, default="active", server_default="active")

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    contract = relationship("InstitutionContract", back_populates="plans", lazy="joined")
    transport_fees = relationship(
        "PlanTransportFee", back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )


class PlanTransportFee(Base):
    """方案層交通費選項。

    心智圖 §二「選方案時帶出」：每方案交通費模式不同，可直接帶出讓心理師選擇；
    使用診間則無交通費。因為一個方案可能有多個選項，故為 1:N。
    """

    __tablename__ = "plan_transport_fees"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(100), nullable=False)  # 如「市區」「跨區」
    amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")

    plan = relationship("InstitutionPlan", back_populates="transport_fees")
