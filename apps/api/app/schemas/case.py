from datetime import date

from pydantic import BaseModel


class CaseCreate(BaseModel):
    name: str
    national_id: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    initial_visit_date: date | None = None
    funding_source: str = "self_pay"
    institution_id: int | None = None
    therapist_id: int
    notes: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    funding_source: str | None = None
    institution_id: int | None = None
    therapist_id: int | None = None
    status: str | None = None
    notes: str | None = None


class CaseResponse(BaseModel):
    id: int
    case_code: str | None = None
    name: str
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    phone_home: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    emergency_phone2: str | None = None
    initial_visit_date: date | None = None
    funding_source: str
    institution_id: int | None = None
    institution_name: str | None = None
    referral_source: str | None = None
    session_location: str | None = None
    therapist_id: int
    therapist_name: str | None = None
    status: str
    notes: str | None = None

    model_config = {"from_attributes": True}
