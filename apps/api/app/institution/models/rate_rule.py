"""費率規則：有序、先匹配先贏。見 07 §6.2。

`when` 是一個條件字典，支援六個變數：session_type / visit_seq / duration_min /
location_kind / time_band / sub_unit，每個變數可以是精確值或 {"gte": n} 這種
簡單比較。沒有 `when`（空字典）代表「其餘情況」的預設規則，通常放在
sort_order 最大的位置。

`price_source="therapist_rate"` 代表這條規則不查 unit_price，而是直接採用
心理師主檔的鐘點費（聊心茶室、遠距抱抱、蛹之生／國泰舊案）。

實際的條件比對邏輯在 app/institution/rules/pricing.py。
"""

from sqlalchemy import Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class InstRateRule(Base):
    __tablename__ = "inst_rate_rules"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("inst_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    when_json = Column(Text, nullable=False, default="{}", server_default="{}")  # JSON 條件字典

    price_source = Column(String(20), nullable=False, default="fixed", server_default="fixed")  # fixed | therapist_rate
    unit_price = Column(Numeric(10, 2), nullable=True)  # price_source="fixed" 時必填
    case_payable = Column(Numeric(10, 2), nullable=True, default=0)  # NULL 時由呼叫端依方案預設值推算
    label = Column(String(100), nullable=True)  # 給行政看的說明，如「第一次無自付」

    plan = relationship("InstPlan", back_populates="rate_rules")
