from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import relationship

from app.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    appointment_number = Column(String(50), unique=True, nullable=False, index=True)
    # 一般預約必填；初診預約在個案建立前為空，改綁 referral_id
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    referral_id = Column(Integer, ForeignKey("referral_requests.id"), nullable=True, index=True)
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
    # 報到狀態：pending 待報到／arrived 已到／absent 未到
    checkin_status = Column(String(20), nullable=False, default="pending", server_default="pending")
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    fee_item = Column(String(30), nullable=True)  # 諮商項目，連動收據名目
    plan_id = Column(Integer, ForeignKey("institution_plans.id"), nullable=True)
    rate_item_id = Column(Integer, ForeignKey("plan_rate_items.id"), nullable=True)
    transport_fee = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    transport_fee_option_id = Column(Integer, ForeignKey("plan_transport_fees.id"), nullable=True)
    video_link = Column(String(500), nullable=True)
    notify_admin_to_forward = Column(Boolean, nullable=False, default=False, server_default="false")
    forwarded_at = Column(DateTime(timezone=True), nullable=True)
    outreach_location = Column(String(300), nullable=True)
    # D1：當次金額（心理師每次預約可填）
    hourly_rate = Column(Numeric(10, 2), nullable=True)
    is_intake = Column(Boolean, nullable=False, default=False, server_default="false")
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
