from sqlalchemy import Column, Date, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    national_id_encrypted = Column(LargeBinary, nullable=True)
    national_id_hmac = Column(String(64), nullable=True, index=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    phone = Column(String(30), nullable=True)
    emergency_contact = Column(String(100), nullable=True)
    initial_visit_date = Column(Date, nullable=True)
    funding_source = Column(String(20), nullable=False, default="self_pay")  # self_pay, institution
    institution_name = Column(String(200), nullable=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="initial")  # initial, ongoing, paused, closed, lost
    notes = Column(Text, nullable=True)

    therapist = relationship("User", back_populates="cases")
    appointments = relationship("Appointment", back_populates="case")
