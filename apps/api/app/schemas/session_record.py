from datetime import date, datetime

from pydantic import BaseModel


class SessionRecordResponse(BaseModel):
    id: int
    appointment_id: int
    appointment_number: str | None = None
    session_date: date
    case_id: int
    case_name: str | None = None
    therapist_id: int
    therapist_name: str | None = None
    session_type: str
    room_id: int | None = None
    fee_category: str
    amount: float
    therapist_share: float
    clinic_share: float
    payment_status: str
    funding_source: str | None = None
    locked_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionRecordUpdatePayment(BaseModel):
    payment_status: str


class SettlementRequest(BaseModel):
    target_date: date | None = None


class SettlementResponse(BaseModel):
    date: str
    executed: int
    skipped: int
