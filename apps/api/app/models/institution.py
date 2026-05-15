from sqlalchemy import Boolean, Column, ForeignKey, Integer, String

from app.database import Base


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    code = Column(String(5), unique=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
