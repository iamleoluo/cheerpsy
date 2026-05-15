from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    start_time: datetime
    end_time: datetime
    amount: float


class AppointmentBatchCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    amount: float
    slots: list["BatchSlot"]


class BatchSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    amount: float | None = None


class AppointmentResponse(BaseModel):
    id: int
    appointment_number: str
    case_id: int
    case_name: str | None = None
    therapist_id: int
    therapist_name: str | None = None
    room_id: int | None = None
    room_name: str | None = None
    session_type: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    amount: float
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
