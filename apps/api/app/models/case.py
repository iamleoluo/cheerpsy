from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, Sequence, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    temp_seq = Column(Integer, Sequence("cases_temp_seq_seq"), nullable=True)
    case_code = Column(String(20), nullable=True, index=True)
    case_number = Column(String(10), unique=True, nullable=True, index=True)
    billing_cycle = Column(String(20), nullable=False, default="once", server_default="once")
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=True)
    national_id_encrypted = Column(LargeBinary, nullable=True)
    national_id_hmac = Column(String(64), nullable=True, index=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    phone = Column(String(50), nullable=True)
    phone_home = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    emergency_contact = Column(String(200), nullable=True)
    emergency_phone = Column(String(50), nullable=True)
    emergency_phone2 = Column(String(50), nullable=True)
    initial_visit_date = Column(Date, nullable=True)
    funding_source = Column(String(20), nullable=False, default="self_pay")
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    referral_source = Column(String(200), nullable=True)
    session_location = Column(String(200), nullable=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="initial")
    case_type = Column(String(20), nullable=False, default="individual", server_default="individual")  # individual / couple
    notes = Column(Text, nullable=True)
    # 結案/復案：status="closed" 時填入，個案資料保留但從列表預設隱藏
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closure_reason = Column(String(500), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_designated = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    therapist = relationship("User", back_populates="cases", foreign_keys=[therapist_id])
    institution = relationship("Institution")
    appointments = relationship("Appointment", back_populates="case")
    # 伴侶案 → 成員連結（僅 case_type='couple' 會有）
    couple_links = relationship(
        "CoupleMember",
        foreign_keys="CoupleMember.couple_case_id",
        viewonly=True,
    )
