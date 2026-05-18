from datetime import date

from pydantic import BaseModel


class ProductSaleCreate(BaseModel):
    sale_date: date
    product_name: str
    amount: float
    quantity: int = 1
    payment_method: str = "cash"
    payment_note: str | None = None


class ProductSaleUpdate(BaseModel):
    sale_date: date | None = None
    product_name: str | None = None
    amount: float | None = None
    quantity: int | None = None
    payment_method: str | None = None
    payment_note: str | None = None


class ProductSaleVoid(BaseModel):
    reason: str | None = None


class ProductSaleResponse(BaseModel):
    id: int
    sale_date: date
    product_name: str
    amount: float
    quantity: int
    payment_method: str | None = None
    payment_note: str | None = None
    receipt_no: str | None = None
    is_void: bool
    void_reason: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}
