"""媒合管理（referral／matching）：諮商需求表送進來後，到媒合出第一次
（初診）預約為止的暫存資料。一旦轉為正式個案（Case），這裡的資料就不再
被讀取——見 document_reference/cheerpsy_v7_spec_extracted.md「媒合管理」。

狀態機（status）：
    new       新增：已建需求表、尚未派案
    matching  媒合中：已派給心理師、等待回覆
    unmatched 不成功／已退回：本輪無人承接或逾時，可重新派案
    accepted  成功轉預約：心理師已承接並提供時段，行政待「轉預約」
    booked    初診已預約：行政已建立正式初診預約，等待報到
    converted 已轉個案：初診有到，已建立/啟用正式個案，離開本列表
    cancelled 取消媒合：個案自行取消或行政取消（可附原因）
    closed    已結案：其他結束原因（如多次未到後放棄）
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True)
    referral_code = Column(String(20), unique=True, nullable=False, index=True)  # YYMMDD+3碼流水號

    # ── 諮商需求表欄位（行政可編輯，心理師唯讀；初診有到後鎖定）───────────
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)
    phone = Column(String(50), nullable=True)
    mode = Column(String(20), nullable=False, default="in_person", server_default="in_person")  # in_person/online/outdoor
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)  # 疑似機構案（僅供媒合參考，實際方案於轉預約時選）
    funding_note = Column(String(200), nullable=True)  # 自由文字，如「衛生局市民方案」
    issues = Column(Text, nullable=True)  # JSON 字串陣列，主述議題勾選
    issue_note = Column(Text, nullable=True)
    designated_therapist_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    source = Column(String(50), nullable=True)  # 轉介來源（親友介紹會觸發雙重關係提醒）
    availability = Column(String(500), nullable=True)  # 可諮商時段（自由文字）
    note = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="new", server_default="new")

    # ── 媒合結果 ──────────────────────────────────────────────────────
    accepted_therapist_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    converted_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    close_reason = Column(String(500), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    institution = relationship("Institution", lazy="joined")
    designated_therapist = relationship("User", foreign_keys=[designated_therapist_id])
    accepted_therapist = relationship("User", foreign_keys=[accepted_therapist_id])
    batches = relationship("ReferralBatch", back_populates="referral", order_by="ReferralBatch.id")
