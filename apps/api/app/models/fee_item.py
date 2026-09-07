"""收費項目主檔（P1，02 §1.2）：開立收據時的「收款項目」下拉來源。

定稿 8 個預設值：諮商／會談／專業評估／心理治療／人際互動治療／摘要報告／
會面交往／工作坊，另外收據開立時可選「其他（自行登打）」存為未歸類——那個
選項不在這張表裡，是 receipts.fee_item_custom_name 欄位（見 receipt.py）。
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.database import Base


class FeeItem(Base):
    __tablename__ = "fee_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
