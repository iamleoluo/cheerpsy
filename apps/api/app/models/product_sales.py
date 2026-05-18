from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func

from app.database import Base


class ProductSale(Base):
    __tablename__ = "product_sales"

    id = Column(Integer, primary_key=True)
    sale_date = Column(Date, nullable=False)
    product_name = Column(String(200), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1, server_default="1")
    payment_method = Column(String(20), nullable=True, default="cash", server_default="cash")
    payment_note = Column(String(200), nullable=True)
    receipt_no = Column(String(30), nullable=True, unique=True)  # P{YYYYMMDD}{seq:04d}
    is_void = Column(Boolean, nullable=False, default=False, server_default="false")
    void_reason = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
