"""容器裡的明細，每筆對應主系統一次諮商（session_record）。

session_record_id 是子系統唯一直接引用主系統事實表的地方（另一處是
enrollment.case_id）。這是刻意允許的——依賴方向規則只禁止「主系統
import 子系統」，子系統讀主系統的表完全沒問題（見 07 §3.2）。
"""

from sqlalchemy import Column, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class InstClaimLine(Base):
    __tablename__ = "inst_claim_lines"
    __table_args__ = (UniqueConstraint("session_record_id", name="uq_claim_line_session_record"),)

    id = Column(Integer, primary_key=True)
    claim_case_id = Column(Integer, ForeignKey("inst_claim_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    session_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=False, index=True)

    claimed_amount = Column(Numeric(10, 2), nullable=False)  # 本筆請款金額，可回溯調整

    # 「登記時數 ≠ 實際時數」的方案（台南地院、台南女中、輔諮南一區），見 07 §4.3。
    # 轉換規則放在方案上（InstPlan.registered_hours_rule 備忘），轉換結果存這裡。
    actual_hours = Column(Numeric(4, 2), nullable=True)
    registered_hours = Column(Numeric(4, 2), nullable=True)
    registered_unit_price = Column(Numeric(10, 2), nullable=True)

    claim_case = relationship("InstClaimCase", back_populates="lines")
