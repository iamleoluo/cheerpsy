from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # doc_pending, appointment_today, claim_ready, payment_due, system
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(200), nullable=True)  # e.g. /claims/5 or /ledger?record=12
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
