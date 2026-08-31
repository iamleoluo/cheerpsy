from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class DailyClosing(Base):
    """每日對帳。完成後鎖定；解鎖修改會寫入 supervisor_reviews。

    月報表的資料來源只有一個：status='closed' 的日。
    """

    __tablename__ = "daily_closings"

    id = Column(Integer, primary_key=True)
    closing_date = Column(Date, unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    cash_total = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    transfer_total = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    unpaid_total = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    note = Column(String(500), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class MonthlyReport(Base):
    """月報表表頭。只存不可推導的欄位。

    已對帳天數／合計金額／心理師收入一律即時聚合自 daily_closings，
    月份由 daily_closings.closing_date 推得，session_records 不掛反向外鍵
    （否則同一筆紀錄會有兩條路徑歸屬到月份，對帳日期一改就可能不一致）。
    """

    __tablename__ = "monthly_reports"

    id = Column(Integer, primary_key=True)
    month = Column(String(7), unique=True, nullable=False)  # YYYY-MM
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    payout_date = Column(Date, nullable=True)  # 結算月的隔月 25 日


class SupervisorReview(Base):
    """主管覆核紀錄：對帳鎖定後解鎖修改的紀錄。

    這是**業務流程**（要有人覆核、要能列待覆核清單），不只是稽核軌跡，
    所以獨立成表而非重用 audit_log。
    """

    __tablename__ = "supervisor_reviews"

    id = Column(Integer, primary_key=True)
    daily_closing_id = Column(Integer, ForeignKey("daily_closings.id", ondelete="CASCADE"), nullable=False, index=True)
    session_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    unlock_reason = Column(String(500), nullable=False)
    unlocked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    unlocked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
