from datetime import date, datetime

from pydantic import BaseModel


class ClaimBatchCreate(BaseModel):
    type: str  # self_pay / institution
    case_id: int | None = None
    institution_id: int | None = None
    billing_cycle: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    session_record_ids: list[int] = []


class ClaimBatchUpdate(BaseModel):
    external_ref: str | None = None
    payment_method: str | None = None
    payment_note: str | None = None
    item_name: str | None = None


class ClaimBatchVerifyAll(BaseModel):
    """空 body 也合法的 admin-verify-all request。"""


class ClaimBatchResponse(BaseModel):
    id: int
    batch_number: str
    external_ref: str | None = None
    type: str
    billing_cycle: str | None = None
    expected_sessions: int | None = None
    institution_id: int | None = None
    institution_name: str | None = None
    case_id: int | None = None
    case_name: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    total_amount: float
    payment_method: str | None = None
    payment_note: str | None = None
    item_name: str | None = None
    status: str
    record_count: int = 0
    confirmed_count: int = 0
    admin_verified_count: int = 0
    created_at: str | None = None
    submitted_at: str | None = None
    received_at: str | None = None
    closed_at: str | None = None
    docs_waived_at: datetime | None = None
    docs_waived_by: int | None = None
    docs_required: bool = True


class ClaimBatchRecordResponse(BaseModel):
    id: int
    session_date: str
    case_name: str | None = None
    therapist_name: str | None = None
    session_type: str
    amount: float
    payment_status: str
    therapist_doc_submitted_at: str | None = None
    admin_verified_at: str | None = None
