from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    status = Column(String(20), nullable=False, default="active")  # active, voided
    void_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="invoice")
