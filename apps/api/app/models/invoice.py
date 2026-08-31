from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    # 三者擇一：預約（舊）／日結紀錄／商品販售
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    session_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    product_sale_id = Column(Integer, ForeignKey("product_sales.id"), nullable=True)
    # 收據編號規則：{館別}{YYYYMMDD}{C|O}{流水3碼}-{檢核碼}
    branch_code = Column(String(2), nullable=False, default="A", server_default="A")
    category = Column(String(1), nullable=False, default="C", server_default="C")  # C 諮商 / O 其他
    print_seq = Column(Integer, nullable=False, default=0, server_default="0")  # 重印次數
    check_code = Column(Integer, nullable=False, default=1, server_default="1")  # 1 開立 2 重印 3 作廢
    status = Column(String(20), nullable=False, default="active")  # active, voided
    void_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="invoice")
