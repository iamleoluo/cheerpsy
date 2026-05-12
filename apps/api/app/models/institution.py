from sqlalchemy import Boolean, Column, Integer, String

from app.database import Base


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
