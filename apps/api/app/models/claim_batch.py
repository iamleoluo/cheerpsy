from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func

from app.database import Base


class ClaimBatch(Base):
    __tablename__ = "claim_batches"

    id = Column(Integer, primary_key=True)
    batch_number = Column(String(50), unique=True, nullable=False)
    external_ref = Column(String(100), nullable=True)
    type = Column(String(20), nullable=False)  # self_pay, institution
    billing_cycle = Column(String(20), nullable=True)
    expected_sessions = Column(Integer, nullable=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    payment_method = Column(String(20), nullable=True)
    payment_note = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="collecting", server_default="collecting")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    docs_waived_at = Column(DateTime(timezone=True), nullable=True)
    docs_waived_by = Column(Integer, ForeignKey("users.id"), nullable=True)
