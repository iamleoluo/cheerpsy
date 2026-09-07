"""Layer 3・核銷案＝容器。見 07 §4.3（2026/09/07 更新為容器模型）。

核心概念：核銷案是一個「容器」，行政隨時可以先開一個空容器，系統依
grouping_mode 把符合的紀錄撈進來。門檻是容量上限，不是阻擋條件——
裝不滿也可以送出（個案做 3 次就不來了，這 3 次照樣核銷）。

收入認列 vs 核銷送件是兩條獨立時間軸（已定案）：
    收入認列 = session_records 的執行月，永遠不變，本容器完全不影響它
    核銷送件 = 本容器的 status 轉換時間，可以晚很多個月
    中間狀態 = session_records.payment_status = 'claiming'（機構應收款／待核銷中）
    入帳只沖銷應收，不搬動收入認列的月份
"""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class InstClaimCase(Base):
    __tablename__ = "inst_claim_cases"

    id = Column(Integer, primary_key=True)
    claim_no = Column(String(20), unique=True, nullable=False)  # YYMM + 流水2碼，如 202607-01
    claim_group_key = Column(String(100), nullable=False, index=True)

    # 容器的收納規則：per_case_count（以個案為單位，容量 N 次）｜period（以時間為單位）
    grouping_mode = Column(String(20), nullable=False, default="period", server_default="period")
    capacity = Column(Integer, nullable=True)  # grouping_mode=per_case_count 時的容量

    # 撈紀錄用的區間，不綁定——送出時才是最終區間（08 決策，見 07 §4.3）
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    status = Column(String(20), nullable=False, default="collecting", server_default="collecting")
    # collecting -> ready -> submitted -> received -> closed；另有 voided

    settlement_mode = Column(String(20), nullable=False, default="claim_then_pay", server_default="claim_then_pay")
    # claim_then_pay | pay_then_claim（儲值型） | pay_no_claim（先撥款不核銷後補收據）

    applied_amount = Column(Numeric(12, 2), nullable=True)
    received_date = Column(Date, nullable=True)
    received_amount = Column(Numeric(12, 2), nullable=True)
    income_tax_amount = Column(Numeric(12, 2), nullable=True)
    transfer_fee = Column(Numeric(10, 2), nullable=True)
    net_received = Column(Numeric(12, 2), nullable=True)  # 申請 − 稅 − 手續費

    locked_at = Column(DateTime(timezone=True), nullable=True)  # 收款後鎖定，改需上層權限
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_reason = Column(Text, nullable=True)

    # 文件豁免（從舊 claim_batches 移植過來的機制，見 services/claim_batch.py
    # 的 apply_doc_waiver/revert_doc_waiver）：免繳文件的機構，行政一鍵把
    # 容器內所有紀錄標記成「視同已提交」，不必等心理師一筆筆確認。
    docs_waived_at = Column(DateTime(timezone=True), nullable=True)
    docs_waived_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lines = relationship("InstClaimLine", back_populates="claim_case", cascade="all, delete-orphan")
