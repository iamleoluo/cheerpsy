from datetime import date, datetime

from pydantic import BaseModel


class CaseCreate(BaseModel):
    name: str
    age: int | None = None
    national_id: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    initial_visit_date: date | None = None
    funding_source: str = "self_pay"
    institution_id: int | None = None
    therapist_id: int
    billing_cycle: str = "once"
    is_designated: bool = False
    notes: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    national_id: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    phone_home: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    emergency_phone2: str | None = None
    referral_source: str | None = None
    session_location: str | None = None
    funding_source: str | None = None
    institution_id: int | None = None
    therapist_id: int | None = None
    status: str | None = None
    billing_cycle: str | None = None
    is_designated: bool | None = None
    notes: str | None = None


class CaseResponse(BaseModel):
    id: int
    temp_seq: int | None = None
    case_code: str | None = None
    case_number: str | None = None
    name: str
    age: int | None = None
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
    billing_cycle: str | None = None
    has_national_id: bool = False
    is_designated: bool = False
    notes: str | None = None
    closed_at: datetime | None = None
    closure_reason: str | None = None

    model_config = {"from_attributes": True}


class CaseCloseRequest(BaseModel):
    """結案請求 — 必須帶呼叫者密碼（防誤觸）。"""
    password: str
    reason: str | None = None


class CaseReopenRequest(BaseModel):
    """復案請求 — 必須帶呼叫者密碼。"""
    password: str
