from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ClaimBatchPlan(Base):
    """核銷案 ↔ 機構方案（Q3：一案可跨方案一起核銷）。

    紀錄仍需「先從方案選定後，再從中挑紀錄」，故方案是挑紀錄的入口。
    """

    __tablename__ = "claim_batch_plans"
    __table_args__ = (
        UniqueConstraint("claim_batch_id", "plan_id", name="uq_claim_batch_plan"),
    )

    id = Column(Integer, primary_key=True)
    claim_batch_id = Column(Integer, ForeignKey("claim_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="CASCADE"), nullable=False)

    plan = relationship("InstitutionPlan", lazy="joined")


class ClaimDocument(Base):
    """心理師依核銷案上傳的附件。

    三類：領據／月次清冊表／其他（銀行帳戶、心理師證照、個案同意書…）。
    讓心理師一次上傳完畢，行政要核銷時再下載。
    """

    __tablename__ = "claim_documents"

    id = Column(Integer, primary_key=True)
    claim_batch_id = Column(Integer, ForeignKey("claim_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    therapist_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(20), nullable=False)  # receipt / monthly_list / other
    file_name = Column(String(300), nullable=False)
    note = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    therapist = relationship("User", lazy="joined")
