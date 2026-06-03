from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    start_time: datetime
    end_time: datetime
    amount: float
    funding_source: str = "self_pay"  # self_pay | institution
    quota_id: int | None = None
    couple_case_id: int | None = None  # 合療：標記場次所屬伴侶案（case_id 為付款方）


class BatchSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    amount: float | None = None
    funding_source: str | None = None
    quota_id: int | None = None


class AppointmentBatchCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    amount: float
    funding_source: str = "self_pay"
    quota_id: int | None = None
    couple_case_id: int | None = None
    slots: list[BatchSlot]


class AppointmentUpdate(BaseModel):
    room_id: int | None = None
    session_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    amount: float | None = None
    funding_source: str | None = None
    quota_id: int | None = None


class AppointmentPaymentUpdate(BaseModel):
    funding_source: str  # self_pay | institution
    quota_id: int | None = None


class AppointmentResponse(BaseModel):
    id: int
    appointment_number: str
    case_id: int
    case_name: str | None = None
    case_type: str = "individual"
    couple_case_id: int | None = None
    couple_name: str | None = None
    is_couple: bool = False
    therapist_id: int
    therapist_name: str | None = None
    room_id: int | None = None
    room_name: str | None = None
    session_type: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    amount: float
    funding_source: str = "self_pay"
    quota_id: int | None = None
    quota_institution_name: str | None = None
    therapist_share: float | None = None
    clinic_share: float | None = None
    visit_seq: int | None = None
    status: str
    batch_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: int
    name: str
    floor: int
    room_code: str
    has_special_equipment: bool
    notes: str | None = None

    model_config = {"from_attributes": True}
