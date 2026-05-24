from datetime import date, datetime

from pydantic import BaseModel


class SessionRecordResponse(BaseModel):
    id: int
    appointment_id: int | None = None
    appointment_number: str | None = None
    session_date: date
    case_id: int | None = None
    case_name: str | None = None
    therapist_id: int
    therapist_name: str | None = None
    session_type: str
    room_id: int | None = None
    fee_category: str
    amount: float
    discount_amount: float = 0
    discount_note: str | None = None
    effective_amount: float
    therapist_share: float
    clinic_share: float
    payment_status: str
    funding_source: str | None = None
    institution_name: str | None = None
    payment_method: str | None = None
    payment_note: str | None = None
    paid_at: datetime | None = None
    claim_number: str | None = None
    receipt_number: str | None = None
    receipt_no: str | None = None
    commission_rate_used: float | None = None
    claim_batch_id: int | None = None
    claim_batch_number: str | None = None
    therapist_doc_submitted_at: datetime | None = None
    locked_at: datetime | None = None
    is_void: bool = False
    void_reason: str | None = None
    parent_record_id: int | None = None
    outcall_bonus: float = 0
    outcall_note: str | None = None
    billing_cycle: str | None = None

    model_config = {"from_attributes": True}


class SplitRequest(BaseModel):
    self_pay_amount: float
    payment_method: str  # cash | transfer
    payment_note: str | None = None
    fee_category: str = "行政規費"


class OutcallBonusRequest(BaseModel):
    amount: float  # set to 0 to clear
    note: str | None = None


class SessionRecordUpdatePayment(BaseModel):
    payment_status: str
    payment_method: str | None = None
    payment_note: str | None = None
    claim_number: str | None = None
    receipt_number: str | None = None


class SessionRecordDirectEdit(BaseModel):
    payment_status: str
    payment_method: str | None = None
    payment_note: str | None = None
    claim_number: str | None = None
    receipt_number: str | None = None


class VoidRequest(BaseModel):
    reason: str | None = None


class DiscountRequest(BaseModel):
    discount_amount: float | None = None
    discount_percent: float | None = None
    discount_note: str | None = None


class PayRequest(BaseModel):
    payment_method: str
    payment_note: str | None = None
    paid_date: date | None = None  # actual collection date; defaults to now() if omitted


class PayBatchRequest(BaseModel):
    record_ids: list[int]
    payment_method: str
    payment_note: str | None = None
    combine_receipt: bool = False
    paid_date: date | None = None  # actual collection date; defaults to now() if omitted


class SettlementRequest(BaseModel):
    target_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None


class SettlementResponse(BaseModel):
    date: str
    executed: int
    skipped: int


class SelfPayCaseStat(BaseModel):
    case_id: int
    case_name: str
    therapist_name: str | None = None
    paid_count: int
    unpaid_count: int
    paid_amount: float
    unpaid_amount: float
    total_count: int
    all_paid: bool
