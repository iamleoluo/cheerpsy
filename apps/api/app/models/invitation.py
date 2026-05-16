from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.database import Base


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    invite_key = Column(String(20), unique=True, nullable=False, index=True)
    type = Column(String(10), nullable=False)  # invite | reset
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=True)  # for invite
    user_code = Column(String(10), nullable=True)  # for invite
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # for reset
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
