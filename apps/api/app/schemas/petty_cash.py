from datetime import date

from pydantic import BaseModel


class PettyCashCreate(BaseModel):
    date: date
    amount: float
    category: str
    description: str | None = None
    receipt_note: str | None = None


class PettyCashResponse(BaseModel):
    id: int
    date: date
    amount: float
    category: str
    description: str | None = None
    receipt_note: str | None = None
    balance_after: float

    model_config = {"from_attributes": True}
