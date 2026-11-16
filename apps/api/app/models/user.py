from sqlalchemy import Boolean, Column, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # admin, therapist, staff（accountant 已刪除，既有帳號由 migration 停用）
    user_code = Column(String(10), unique=True, nullable=True)
    commission_rate = Column(Numeric(4, 2), nullable=True)
    base_price = Column(Numeric(10, 2), nullable=True)  # therapist default appointment fee
    is_active = Column(Boolean, default=True, nullable=False)
    # False = 名單制心理師：可被預約與派案，但沒有登入帳號。
    # 仍是 users 的一列，因此 appointments/referrals/payouts 的外鍵都不必改。
    has_account = Column(Boolean, nullable=False, default=True, server_default="true")
    # iCal 訂閱 token：讓心理師把班表訂閱進 Google 日曆（單向，不需 OAuth）
    ical_token = Column(String(64), unique=True, nullable=True)
    # Google 日曆分享用的 Gmail（心理師用，由行政／管理員填；與登入 email 無關）。
    # 名單制心理師沒有登入帳號，所以不能沿用 email。
    gcal_share_email = Column(String(320), nullable=True)

    cases = relationship("Case", back_populates="therapist", foreign_keys="[Case.therapist_id]")
    appointments = relationship("Appointment", back_populates="therapist", foreign_keys="[Appointment.therapist_id]")
