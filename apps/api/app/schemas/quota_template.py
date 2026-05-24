from datetime import date, datetime

from pydantic import BaseModel


class QuotaTemplateCreate(BaseModel):
    institution_id: int
    name: str
    total_count: int
    notes: str | None = None


class QuotaTemplateUpdate(BaseModel):
    name: str | None = None
    total_count: int | None = None
    notes: str | None = None


class QuotaTemplateResponse(BaseModel):
    id: int
    institution_id: int
    institution_name: str | None = None
    name: str
    total_count: int
    notes: str | None = None
    created_by: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuotaTemplateApply(BaseModel):
    case_ids: list[int]
    valid_from: date
    valid_until: date
