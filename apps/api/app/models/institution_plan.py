from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstitutionPlan(Base):
    """機構方案（由合約開出的年度方案）。

    個案的機構扣打 case_institution_quotas 掛在這一層。
    per_person_count / annual_total_count 為 NULL 代表「不限」。
    見 document_reference/gap_analysis.md §1.1 #6。
    """

    __tablename__ = "institution_plans"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("institution_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 公告方案名

    # 核銷窗口（與合約承辦人可能不同）
    claim_unit = Column(String(200), nullable=True)
    claim_contact = Column(String(100), nullable=True)
    claim_phone = Column(String(50), nullable=True)

    # ── 額度（問題5）──
    # count 以次數計／amount 以金額計（如國軍一年 $149,000）
    quota_unit = Column(String(10), nullable=False, default="count", server_default="count")
    # NULL = 不限
    per_person_count = Column(Integer, nullable=True)
    annual_total_count = Column(Integer, nullable=True)
    per_person_amount = Column(Numeric(12, 2), nullable=True)
    annual_total_amount = Column(Numeric(12, 2), nullable=True)
    # 容愛協會：每月最多 4 次、累計最多 24 次（雙重限制）
    per_person_monthly_limit = Column(Integer, nullable=True)
    # 警局、奇美家照：基本 6 次，經評估後可再延長 3 次
    extension_sessions = Column(Integer, nullable=True)

    # ── 核銷門檻（問題1）──
    # 個案需累積達 N 次才可送核銷（人事處系列 4 次、脆弱家庭 8 次、社工支持 4 次）
    claim_threshold_sessions = Column(Integer, nullable=True)

    # ── 價格來源（問題7）──
    # contract_fixed 合約談定固定價（多數）
    # therapist_rate 依心理師鐘點費（聊心茶室、遠距抱抱、蛹之生／國泰舊案）
    pricing_mode = Column(String(20), nullable=False, default="contract_fixed", server_default="contract_fixed")

    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    notes = Column(String(1000), nullable=True)

    # active（使用中）/ exhausted（已用罄）/ expired（已過期）
    status = Column(String(20), nullable=False, default="active", server_default="active")

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    contract = relationship("InstitutionContract", back_populates="plans", lazy="joined")
    rate_items = relationship(
        "PlanRateItem", back_populates="plan", cascade="all, delete-orphan",
        lazy="selectin", order_by="PlanRateItem.sort_order",
    )
    transport_fees = relationship(
        "PlanTransportFee", back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )


class PlanTransportFee(Base):
    """方案層交通費選項。

    心智圖 §二「選方案時帶出」：每方案交通費模式不同，可直接帶出讓心理師選擇；
    使用診間則無交通費。因為一個方案可能有多個選項，故為 1:N。
    """

    __tablename__ = "plan_transport_fees"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(100), nullable=False)  # 如「市區」「跨區」
    amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")

    plan = relationship("InstitutionPlan", back_populates="transport_fees")


class PlanRateItem(Base):
    """方案價目表（問題2／3／6）。

    Phase 1a 假設「一個方案一個鐘點費」，但清冊裡至少 10 個方案的收費會依
    服務型態、時長、第幾次諮商而不同，例如：
        家防中心   個別 $1,400/hr、家族 $2,000/hr
        緯穎智造   個別 $2,600/50分、入廠 $5,200/100分、緊急 $3,500/50分
        國軍       個別 $1,600、講座 $2,000/hr、本島團輔 $6,000/1.5hr
        衛生局市民 第1次個案免費(機構$1,600)、第2次個案$200(機構$1,400)
        蛹之生     第1次 $2,000、第2次 $1,840、第3次起 $2,070
    """

    __tablename__ = "plan_rate_items"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("institution_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    service_type = Column(String(30), nullable=True)     # NULL = 不限
    duration_minutes = Column(Integer, nullable=True)
    # 適用第幾次；NULL = 不限。用於「第1次免費、第3次起漲價」這種階梯
    session_seq_from = Column(Integer, nullable=True)
    session_seq_to = Column(Integer, nullable=True)

    total_amount = Column(Numeric(10, 2), nullable=False)
    self_pay_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    # 問題6：雙源分攤時，兩張收據的品項名稱可以不同
    #   個案端常是「場地費」「行政規費」；機構端是「諮商鐘點費」
    self_pay_receipt_item = Column(String(100), nullable=True)
    institution_receipt_item = Column(String(100), nullable=True)

    # 問題3：核銷單上登記的時數與單價，與實際諮商時數不同時填寫
    #   台南地院 實際1小時$1,600 → 登記2小時×$800
    #   台南女中 實際1小時$1,500 → 登記1.5小時×$1,000
    claim_hours = Column(Numeric(5, 2), nullable=True)
    claim_unit_rate = Column(Numeric(10, 2), nullable=True)

    is_no_show_fee = Column(Boolean, nullable=False, default=False, server_default="false")
    note = Column(String(500), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    plan = relationship("InstitutionPlan", back_populates="rate_items")

    @property
    def institution_claim_amount(self):
        return (self.total_amount or 0) - (self.self_pay_amount or 0)
