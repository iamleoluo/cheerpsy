from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import relationship

from app.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    appointment_number = Column(String(50), unique=True, nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    session_type = Column(String(20), nullable=False)  # in_person, online, outdoor
    time_range = Column(TSTZRANGE, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    # booked / executed / cancelled / no_show（Phase 1b 新增 no_show）
    status = Column(String(20), nullable=False, default="booked")
    # advance_notice 24h前請假 $0 / late_cancel 臨時取消 / no_notice 無故未到
    no_show_type = Column(String(20), nullable=True)
    no_show_fee = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    funding_source = Column(String(20), nullable=False, default="self_pay", server_default="self_pay")  # self_pay | institution
    quota_id = Column(Integer, ForeignKey("case_institution_quotas.id"), nullable=True)
    visit_seq = Column(Integer, nullable=True)
    batch_id = Column(String(50), nullable=True, index=True)
    # 合療標記：有值 = 這是某伴侶案的合療場次（case_id 仍為付款方）
    couple_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="appointments", foreign_keys=[case_id])
    couple_case = relationship("Case", foreign_keys=[couple_case_id])
    therapist = relationship("User", back_populates="appointments", foreign_keys=[therapist_id])
    room = relationship("Room")
    session_record = relationship("SessionRecord", back_populates="appointment", uselist=False)
    invoice = relationship("Invoice", back_populates="appointment", uselist=False)
    reminders = relationship("ReminderLog", back_populates="appointment")
