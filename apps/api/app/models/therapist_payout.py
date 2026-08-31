from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String



from app.database import Base


class TherapistPayout(Base):
    __tablename__ = "therapist_payouts"

    id = Column(Integer, primary_key=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payout_month = Column(String(7), nullable=False)  # YYYY-MM
    # 心智圖 §四.4 心理師當月收入五欄；total_amount 為合計
    counseling_income = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    lecture_fee = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    supervision_income = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    venue_deduction = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, paid
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class PayoutDetail(Base):
    __tablename__ = "payout_details"

    id = Column(Integer, primary_key=True)
    payout_id = Column(Integer, ForeignKey("therapist_payouts.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=False)
    # Q22/Q23：鐘點費回溯修改不自動重算酬勞，改由人工調整並留稽核
    amount = Column(Numeric(12, 2), nullable=True)
    is_manually_adjusted = Column(Boolean, nullable=False, default=False, server_default="false")
    rate_changed_flag = Column(Boolean, nullable=False, default=False, server_default="false")
