from sqlalchemy import Boolean, Column, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # admin, accountant, therapist, staff
    therapist_code = Column(String(10), unique=True, nullable=True)
    commission_rate = Column(Numeric(4, 2), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    cases = relationship("Case", back_populates="therapist")
    appointments = relationship("Appointment", back_populates="therapist")
