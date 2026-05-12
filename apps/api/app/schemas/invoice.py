from datetime import datetime

from pydantic import BaseModel


class InvoiceCreate(BaseModel):
    appointment_id: int


class InvoiceVoid(BaseModel):
    void_reason: str


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    appointment_id: int
    appointment_number: str | None = None
    case_name: str | None = None
    therapist_name: str | None = None
    amount: float | None = None
    status: str
    void_reason: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
