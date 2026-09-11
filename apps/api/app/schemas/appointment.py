from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"  # 型式：in_person / online / outdoor
    # 諮商型態（機構費率規則的計價維度，07 §6.2）與服務地點。與 session_type
    # 不同軸：家防中心的 個別/親職/家族 三種價都是「現場」。
    consult_type: str = "individual"  # individual/couple/family/parenting/group/lecture/meeting
    location_kind: str = "clinic"  # clinic / home / onsite / offsite
    start_time: datetime
    end_time: datetime
    # amount 在指定 plan_id 時可省略（金額由機構子系統報價決定）；未指定 plan_id
    # 時仍為必填（自費／舊機構路徑）。見 create_appointment() 的驗證。
    amount: float | None = None
    funding_source: str = "self_pay"  # self_pay | institution
    quota_id: int | None = None  # 舊路徑：case_institution_quotas。與 plan_id 互斥
    # 機構合約子系統整合（V2升級計畫 07 §5.2、§7.1）：指定後改走
    # funding_registry.quote()/reserve()，忽略 funding_source/quota_id。
    plan_id: int | None = None
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
    consult_type: str = "individual"
    location_kind: str = "clinic"
    # amount 在指定 plan_id 時可省略（同 AppointmentCreate）
    amount: float | None = None
    funding_source: str = "self_pay"
    quota_id: int | None = None
    # 機構方案批次預約（原本批次完全不支援 plan_id，機構案沒辦法一次建六週）
    plan_id: int | None = None
    couple_case_id: int | None = None
    slots: list[BatchSlot]


class AppointmentUpdate(BaseModel):
    room_id: int | None = None
    session_type: str | None = None
    consult_type: str | None = None
    location_kind: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    amount: float | None = None
    funding_source: str | None = None
    quota_id: int | None = None


class AppointmentPaymentUpdate(BaseModel):
    funding_source: str  # self_pay | institution
    quota_id: int | None = None


class CheckInRequest(BaseModel):
    """P1 出席驅動核心端點的請求體。見 01 §A1、02 §4.1。"""

    status: str  # "arrived" | "no_show"
    no_show_reason: str | None = None  # case_leave | last_minute_cancel | unreachable | other
    no_show_note: str | None = None
    no_show_followup: str | None = None  # 催繳方式，具體選項待丙5確認（01 §F 丙5）


class PaymentStepRequest(BaseModel):
    """報到流程步驟2：收款。見 01 §A2。"""

    payment_method: str  # cash | transfer
    payment_note: str | None = None  # transfer 時為必填（如帳戶末五碼）


class PaymentStepResponse(BaseModel):
    session_record_id: int
    payable_amount: float  # 應收金額（case_payable，缺省時為 amount 全額）
    copay_collected_at: datetime
    copay_payment_method: str
    copay_payment_note: str | None = None

    model_config = {"from_attributes": True}


class IssueReceiptRequest(BaseModel):
    """報到流程步驟3：開立收據。見 01 §A2。fee_item_id 與 fee_item_custom_name 二擇一。"""

    fee_item_id: int | None = None
    fee_item_custom_name: str | None = None  # 「其他（自行登打）」，存為未歸類
    note: str | None = None


class IssueReceiptResponse(BaseModel):
    id: int
    receipt_no: str
    amount: float
    fee_item_name: str | None = None  # 主檔名稱或自訂名稱，前端顯示用
    note: str | None = None
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AppointmentResponse(BaseModel):
    id: int
    appointment_number: str
    case_id: int
    case_name: str | None = None
    # 診間格第一行要印「個案｜性別 · 病歷號」（v7 樣本）。兩者與姓名一樣可識別
    # 個人，所以跟 case_name 走**同一道**隱私閘門 can_see_name，不另開一條路。
    case_number: str | None = None
    gender: str | None = None
    case_type: str = "individual"
    couple_case_id: int | None = None
    couple_name: str | None = None
    is_couple: bool = False
    therapist_id: int
    therapist_name: str | None = None
    room_id: int | None = None
    room_name: str | None = None
    session_type: str
    consult_type: str = "individual"
    location_kind: str = "clinic"
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
    # 機構合約子系統報價快照的攤平欄位（07 §4.2）。plan_name 不是獨立欄位，是從
    # appt.plan_quote（JSONB 快照）裡讀出來的——主系統不查 inst_plans，直接讀
    # 自己存的快照，這正是「報價快照」設計要達成的效果（07 §2.1）。
    plan_id: int | None = None
    plan_name: str | None = None
    case_payable: float | None = None
    institution_payable: float | None = None
    compensation_mode: str | None = None
    # 出席狀態機（P1，01 §A1）
    check_in_status: str = "pending"
    checked_in_at: datetime | None = None
    no_show_reason: str | None = None
    no_show_note: str | None = None
    no_show_followup: str | None = None
    # 報到三步驟（收款/開據）的目前狀態，前端用來決定顯示哪一步（01 §A2）
    copay_collected_at: datetime | None = None
    copay_payment_method: str | None = None
    receipt_no: str | None = None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: int
    name: str
    floor: int
    room_code: str
    has_special_equipment: bool
    notes: str | None = None

    model_config = {"from_attributes": True}
