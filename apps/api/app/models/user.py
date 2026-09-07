from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # admin, accountant, therapist, staff
    user_code = Column(String(10), unique=True, nullable=True)
    commission_rate = Column(Numeric(4, 2), nullable=True)
    base_price = Column(Numeric(10, 2), nullable=True)  # therapist default appointment fee
    is_active = Column(Boolean, default=True, nullable=False)

    # P0（V2升級計畫 02 §8）：實習心理師共用帳號。登入時前端另外收一次
    # actor_name 放進 JWT claim，不落地在這張表；is_shared_account 只是開關。
    is_shared_account = Column(Boolean, default=False, nullable=False, server_default="false")
    # 暫待清單預留欄位，督導配對機制尚未定案，先建欄位不使用。見 01 §F 丁 3。
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 機構合約子系統：督導收費模式（場地租借 b4 用，見 07 §4.1）。
    # A=櫃台代收 / B=心理師自收場地費回扣；欄位已建，資料待心理師主檔提供（甲3）。
    supervision_fee_mode = Column(String(10), nullable=True)
    supervision_split_rate = Column(Numeric(4, 2), nullable=True)
    supervision_split_amount = Column(Numeric(10, 2), nullable=True)

    cases = relationship("Case", back_populates="therapist", foreign_keys="[Case.therapist_id]")
    appointments = relationship("Appointment", back_populates="therapist", foreign_keys="[Appointment.therapist_id]")
