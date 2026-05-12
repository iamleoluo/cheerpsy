from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String

from app.database import Base


class SessionRecord(Base):
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    session_date = Column(Date, nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_type = Column(String(20), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    fee_category = Column(String(20), nullable=False, default="counseling")
    amount = Column(Numeric(10, 2), nullable=False)
    payment_status = Column(String(20), nullable=False, default="unpaid")
    payment_method = Column(String(20), nullable=True)  # cash, transfer
    payment_note = Column(String(200), nullable=True)  # e.g. bank account last 5 digits
    claim_number = Column(String(100), nullable=True)
    receipt_number = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    from sqlalchemy.orm import relationship

    appointment = relationship("Appointment", back_populates="session_record")
