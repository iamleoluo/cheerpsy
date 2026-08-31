from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstitutionContract(Base):
    """機構合約（機構 → 合約 → 方案 三層的中間層）。

    合約定義「錢的規則」：鐘點費、個案自付額、核銷上限。
    下一層 institution_plans 再依合約開出年度方案與額度。
    見 document_reference/gap_analysis.md §1.1 #5。
    """

    __tablename__ = "institution_contracts"

    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 合約 / 公告方案名稱
    eligibility = Column(String(500), nullable=True)  # 方案身份條件，如「15-45歲民眾」

    # 方案鐘點費＝該次諮商總價（含個案自付額）；差額為機構請款額
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    self_pay_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")

    # 總核銷上限：金額 / 次數 / 不限
    cap_type = Column(String(20), nullable=False, default="unlimited", server_default="unlimited")
    cap_value = Column(Numeric(12, 2), nullable=True)  # cap_type='unlimited' 時為 NULL

    contact_person = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)

    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    institution = relationship("Institution", lazy="joined")
    plans = relationship("InstitutionPlan", back_populates="contract", cascade="all, delete-orphan")
