from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class ReminderLog(Base):
    __tablename__ = "reminder_log"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    contact_result = Column(String(20), nullable=False)  # confirmed, wants_cancel, no_answer
    notes = Column(Text, nullable=True)
    contacted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    contacted_at = Column(DateTime(timezone=True), server_default=func.now())

    from sqlalchemy.orm import relationship

    appointment = relationship("Appointment", back_populates="reminders")
