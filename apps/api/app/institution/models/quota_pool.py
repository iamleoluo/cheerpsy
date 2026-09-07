"""額度池：方案層級的總量，可跨多個方案共用。

例：國軍-個別／講座／本島團輔／外島團輔 四個方案共用一個 $149,000/年 的池；
15-45青壯 378 次/年的池只有它自己一個方案用。見 07 §6.1。

unit: count | amount。remaining 由 used_amount 反推，不另存，避免兩份數字
不同步——`consumed_total` 才是唯一的持久化欄位。
"""

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class InstQuotaPool(Base):
    __tablename__ = "inst_quota_pools"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("inst_contracts.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 如「國軍年度總額度」
    unit = Column(String(10), nullable=False, default="count", server_default="count")  # count | amount
    total_limit = Column(Numeric(12, 2), nullable=True)  # NULL = 不限
    consumed_total = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)

    plans = relationship("InstPlan", back_populates="quota_pool")
