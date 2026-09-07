"""櫃檯報到流程步驟3「開立收據」的持久化紀錄（P1，02 §1.2）。

跟既有 app/routers/receipts.py 的關係：那支只做 PDF 渲染，前端傳什麼就印
什麼、不落地存檔（見 01 研究附錄：「POST 直接渲染前端送來的內容，DB 只做
存在性檢查」）。這張表是新的、專門給「報到當場開立」這條路徑用，會員真的
落地存一筆紀錄。兩者暫時並存，尚未整合——那是之後的事，不在這輪範圍。

收據編號規則（receipt_no）：01 §C4／07 §乙1 明確標記「待你與診療所談」，
三份文件目前有三套規則互相矛盾。這裡先沿用 SessionRecord.receipt_no 已經
在用的 R{YYYYMMDD}{seq:04d} 格式（services/settlement.py:next_receipt_no），
維持系統內部一致，格式定案後只要改 _next_appointment_receipt_no() 一處。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func

from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)
    receipt_no = Column(String(30), unique=True, nullable=False)
    session_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    fee_item_id = Column(Integer, ForeignKey("fee_items.id"), nullable=True)
    fee_item_custom_name = Column(String(100), nullable=True)  # 「其他（自行登打）」，存為未歸類
    note = Column(String(200), nullable=True)
    status = Column(String(10), nullable=False, default="issued", server_default="issued")  # issued | voided
    void_reason = Column(String(200), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
