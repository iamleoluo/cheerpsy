from datetime import date

from pydantic import BaseModel


class QuotaCreate(BaseModel):
    institution_id: int
    total_count: int
    valid_from: date
    valid_until: date
    note: str | None = None


class QuotaUpdate(BaseModel):
    total_count: int | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    note: str | None = None


class QuotaResponse(BaseModel):
    id: int
    case_id: int
    case_name: str | None = None
    institution_id: int
    institution_name: str | None = None
    total_count: int
    used_count: int
    remaining: int
    valid_from: date
    valid_until: date
    note: str | None = None

    model_config = {"from_attributes": True}
