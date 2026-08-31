from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base

# ---------------------------------------------------------------------------
# 媒合狀態（referral_requests.status）
#   new          新增：已建需求表、尚未派案
#   matching     媒合中：已派給心理師、等待回覆
#   failed       不成功：心理師婉拒，可重新派案
#   converted    成功轉預約：心理師承接，行政排初診
#   cancelled    取消媒合：個案自行取消
#   closed       已結案：我方結束（聯繫不上／所有心理師皆無法配合）
#   intake_done  初診有到：已產生病歷號，案件離開媒合列表轉入個案管理
# ---------------------------------------------------------------------------
REFERRAL_STATUS = (
    "new", "matching", "failed", "converted", "cancelled", "closed", "intake_done",
)

# 派案對象的回覆狀態（referral_dispatch_targets.status）
#   pending      待回覆
#   accepted     有意願承接
#   declined     無意願承接（婉拒）
#   taken        被他人承接
#   expired      已退回（逾 3 個自然日未回覆自動退回）
#   released     承接後釋出（承接後因時段無法配合轉出）
TARGET_STATUS = ("pending", "accepted", "declined", "taken", "expired", "released")

# 婉拒原因
DECLINE_REASONS = ("not_my_field", "fully_booked", "dual_relationship", "other")

# 取消媒合原因
CANCEL_REASONS = (
    "match_failed",          # 媒合不成功
    "time_unavailable",      # 指定時間無法安排
    "designated_unavailable",  # 指定心理師無法安排
    "all_unavailable",       # 所有心理師皆無法安排
)


class ReferralRequest(Base):
    """諮商需求表 / 媒合案主體。

    派案碼 dispatch_code = YYMMDD + 流水號3碼，建立需求表時產生。
    初診有到後另外產生病歷號，兩碼並存以利追溯媒合來源。
    """

    __tablename__ = "referral_requests"

    id = Column(Integer, primary_key=True)
    dispatch_code = Column(String(12), unique=True, nullable=False, index=True)

    # 個案基本資料（初診有到前個資住在這裡，行政可編輯、心理師唯讀）
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)
    phone = Column(String(50), nullable=True)

    # 管道來源（自己有意願／親友介紹／自行前來／社群媒體／他院所推薦／EAP／機構轉介）
    referral_source = Column(String(100), nullable=True)
    # 親友介紹需提示雙重關係
    chief_complaint = Column(String(500), nullable=True)   # 主述議題
    complaint_note = Column(Text, nullable=True)           # 議題補充說明（選填）

    # 諮商型態：individual／couple／family_group
    consultation_mode = Column(String(30), nullable=False, default="individual")
    # 伴侶／會面交往需第二位個案姓名
    partner_name = Column(String(100), nullable=True)

    # 收費模式：self_pay 自費／institution 機構
    funding_source = Column(String(20), nullable=False, default="self_pay")
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), nullable=False, default="new", server_default="new")
    cancel_reason = Column(String(40), nullable=True)
    cancel_note = Column(String(500), nullable=True)

    # 初診
    intake_appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    intake_at = Column(DateTime(timezone=True), nullable=True)
    no_show_reason = Column(String(500), nullable=True)
    # 初診有到後產生的個案（病歷號在 cases.case_number）
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    plan = relationship("InstitutionPlan", lazy="joined")
    # cases.referral_id 與本表 case_id 互指，需明確指定 join 路徑
    case = relationship("Case", lazy="joined", foreign_keys=[case_id])
    dispatches = relationship(
        "ReferralDispatch",
        back_populates="referral",
        cascade="all, delete-orphan",
        order_by="ReferralDispatch.seq",
    )
    designations = relationship(
        "ReferralDesignation", cascade="all, delete-orphan", lazy="selectin"
    )


class ReferralDesignation(Base):
    """指定心理師（上限 3 位）。未指定則本表無列。"""

    __tablename__ = "referral_designations"

    id = Column(Integer, primary_key=True)
    referral_id = Column(
        Integer, ForeignKey("referral_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    therapist_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    therapist = relationship("User", lazy="joined")


class ReferralDispatch(Base):
    """派案批次。子列表一列＝一批次（第幾次派案）。

    一批次可同時發給 1–3 位心理師，先回先得。
    """

    __tablename__ = "referral_dispatches"

    id = Column(Integer, primary_key=True)
    referral_id = Column(
        Integer, ForeignKey("referral_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq = Column(Integer, nullable=False)  # 第幾次派案，從 1 起
    # open 進行中／accepted 已有人承接／failed 全數婉拒／expired 逾期退回／cancelled
    status = Column(String(20), nullable=False, default="open", server_default="open")
    dispatched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    referral = relationship("ReferralRequest", back_populates="dispatches")
    targets = relationship(
        "ReferralDispatchTarget",
        back_populates="dispatch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReferralDispatchTarget(Base):
    """一批次派給某位心理師的邀請與其回覆。"""

    __tablename__ = "referral_dispatch_targets"

    id = Column(Integer, primary_key=True)
    dispatch_id = Column(
        Integer, ForeignKey("referral_dispatches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    therapist_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    decline_reason = Column(String(40), nullable=True)
    decline_note = Column(String(500), nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    # 逾 1 個自然日提醒、逾 3 個自然日自動退回
    reminded_at = Column(DateTime(timezone=True), nullable=True)

    dispatch = relationship("ReferralDispatch", back_populates="targets")
    therapist = relationship("User", lazy="joined")
    slots = relationship(
        "ReferralSlotOffer",
        back_populates="target",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ReferralSlotOffer.seq",
    )


class ReferralSlotOffer(Base):
    """心理師承接時提供的可預約時段（第 1 個必填，2/3 選填）。"""

    __tablename__ = "referral_slot_offers"

    id = Column(Integer, primary_key=True)
    target_id = Column(
        Integer, ForeignKey("referral_dispatch_targets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    seq = Column(Integer, nullable=False)  # 1..3
    slot_date = Column(Date, nullable=False)
    start_time = Column(String(5), nullable=False)  # HH:MM
    end_time = Column(String(5), nullable=False)
    # 行政最終選定的時段標記
    is_selected = Column(Integer, nullable=False, default=0, server_default="0")

    target = relationship("ReferralDispatchTarget", back_populates="slots")
