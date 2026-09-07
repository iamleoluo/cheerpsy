from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    table_name = Column(String(100), nullable=False, index=True)
    record_id = Column(Integer, nullable=False)
    # P0 修正：原本 String(10) 放不下 "ADMIN_VERIFY_ALL" 等既有寫入值，會在正式環境丟
    # value too long for type character varying(10)。見 V2升級計畫 01 §C6。
    operation = Column(String(32), nullable=False)  # INSERT, UPDATE, DELETE, VOID, CLOSE, ADMIN_VERIFY_ALL...
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # 共用帳號（is_shared_account=true）登入時自填的姓名快照，與 changed_by(user_id) 並存。
    # 見 V2升級計畫 02 §8。一般帳號留 NULL，畫面顯示回退到 changed_by 對應的 user.name。
    actor_name = Column(String(100), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    before_data = Column(JSONB, nullable=True)
    after_data = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
