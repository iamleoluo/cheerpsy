from datetime import date, datetime

from pydantic import BaseModel


class QuotaTemplateCreate(BaseModel):
    institution_id: int
    name: str
    total_count: int
    notes: str | None = None
    default_valid_from: date | None = None
    default_valid_until: date | None = None


class QuotaTemplateUpdate(BaseModel):
    name: str | None = None
    total_count: int | None = None
    notes: str | None = None
    default_valid_from: date | None = None
    default_valid_until: date | None = None
    clear_default_valid_from: bool = False
    clear_default_valid_until: bool = False


class QuotaTemplateResponse(BaseModel):
    id: int
    institution_id: int
    institution_name: str | None = None
    name: str
    total_count: int
    notes: str | None = None
    default_valid_from: date | None = None
    default_valid_until: date | None = None
    created_by: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuotaTemplateApply(BaseModel):
    case_ids: list[int]
    # 套用時可選；若為 None 則套用範本的 default 值（也可能仍為 None = 永久）
    valid_from: date | None = None
    valid_until: date | None = None
