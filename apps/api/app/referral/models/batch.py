"""派案批次：行政一次可以同時詢問 1–3 位心理師（先回先得）。一個
referral 底下可以有多個批次（重新派案），子列表即依此展開，見
cheerpsy_v7_spec_extracted.md「媒合管理」⑤。
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ReferralBatch(Base):
    __tablename__ = "referral_batches"

    id = Column(Integer, primary_key=True)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=False, index=True)
    batch_seq = Column(Integer, nullable=False)  # 第幾次派案（1, 2, 3...）
    is_open = Column(Boolean, nullable=False, default=True, server_default="true")  # 是否仍等待回覆
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    referral = relationship("Referral", back_populates="batches")
    members = relationship("ReferralBatchMember", back_populates="batch", order_by="ReferralBatchMember.id")


class ReferralBatchMember(Base):
    """一位被詢問的心理師在某批次裡的回覆狀態。

    reply_status: pending(未回覆) / accepted(承接) / declined(無意願承接) /
                  superseded(已被他人承接) / expired(逾時未回覆) /
                  released(承接後釋出)
    """

    __tablename__ = "referral_batch_members"

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("referral_batches.id"), nullable=False, index=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reply_status = Column(String(20), nullable=False, default="pending", server_default="pending")
    decline_reason = Column(String(50), nullable=True)  # unavailable / not_specialty / dual_relationship / other
    proposed_slots = Column(Text, nullable=True)  # JSON 字串陣列，最多 3 個 ISO 時間字串
    replied_at = Column(DateTime(timezone=True), nullable=True)

    batch = relationship("ReferralBatch", back_populates="members")
    therapist = relationship("User")
