from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.database import Base


class TherapistPayout(Base):
    __tablename__ = "therapist_payouts"

    id = Column(Integer, primary_key=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payout_month = Column(String(7), nullable=False)  # YYYY-MM
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, paid
    paid_at = Column(DateTime(timezone=True), nullable=True)


class PayoutDetail(Base):
    __tablename__ = "payout_details"

    id = Column(Integer, primary_key=True)
    payout_id = Column(Integer, ForeignKey("therapist_payouts.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=False)
