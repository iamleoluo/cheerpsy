from datetime import date

from pydantic import BaseModel


class QuotaCreate(BaseModel):
    institution_id: int
    total_count: int
    valid_from: date | None = None   # None = 無起日下限
    valid_until: date | None = None  # None = 無迄日上限
    note: str | None = None


class QuotaUpdate(BaseModel):
    total_count: int | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    clear_valid_from: bool = False   # True 時主動清空為 NULL
    clear_valid_until: bool = False
    note: str | None = None


class QuotaResponse(BaseModel):
    id: int
    case_id: int
    case_name: str | None = None
    institution_id: int
    institution_name: str | None = None
    total_count: int
    used_count: int
    reserved_count: int = 0   # 已預約但未結算（booked appointments）
    remaining: int            # 實際可用 = total - used - reserved
    valid_from: date | None = None
    valid_until: date | None = None
    note: str | None = None

    model_config = {"from_attributes": True}
