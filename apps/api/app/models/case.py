from sqlalchemy import Column, Date, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    case_code = Column(String(20), nullable=True, index=True)
    name = Column(String(100), nullable=False)
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
    notes = Column(Text, nullable=True)

    therapist = relationship("User", back_populates="cases")
    institution = relationship("Institution")
    appointments = relationship("Appointment", back_populates="case")
