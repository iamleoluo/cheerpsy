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
    # 薪酬模式（07 §8.2）：commission 抽成 / kickback 回饋（扣項）/ none 無勞務。
    # 09 §4.3 要求「我的酬勞」依這三種分區呈現——欄位在 models 上一直都有，
    # 只是沒攤平到 schema，前端拿不到就分不了區。
    compensation_mode: str | None = None
    clinic_share: float
    payment_status: str
    funding_source: str | None = None
    institution_name: str | None = None
    payment_method: str | None = None
    payment_note: str | None = None
    paid_at: datetime | None = None
    claim_number: str | None = None
    receipt_number: str | None = None
    # ⚠️ session_records.receipt_no 是**預先配發**的號碼：build_session_record()
    # 在建立場次時就配好（settlement.py:99），而同一行下面 payment_status 還是
    # 'unpaid'。它代表「這筆將來會用的收據號」，**不代表收據已經開立**。
    #
    # 真正「已開立」的憑證在 receipts 表（status='issued'），由報到三步驟的第 3 步
    # POST /appointments/{id}/receipt 產生，而且那支端點會擋：尚未收款不准開立。
    #
    # 兩個欄位同名不同義，跟 10 §2 那個「兩個都叫 session_type」是同一類陷阱。
    # 畫面要顯示「收據編號」時請用 issued_receipt_no，不要用 receipt_no。
    receipt_no: str | None = None
    issued_receipt_no: str | None = None
    commission_rate_used: float | None = None
    claim_batch_id: int | None = None
    claim_batch_number: str | None = None
    therapist_doc_submitted_at: datetime | None = None
    admin_verified_at: datetime | None = None
    admin_verified_by: int | None = None
    locked_at: datetime | None = None
    is_void: bool = False
    void_reason: str | None = None
    parent_record_id: int | None = None
    outcall_bonus: float = 0
    outcall_note: str | None = None
    billing_cycle: str | None = None
    # 機構合約子系統報價快照的攤平欄位（同 appointments，見 08 §5.1）。
    # 日報表／應收帳冊要同時顯示「個案自付額」與「機構請款額」兩欄，缺這幾
    # 個欄位就只能顯示 amount 全額，分不出這筆錢誰付多少（09 §1.4a）。
    plan_name: str | None = None
    case_payable: float | None = None
    institution_payable: float | None = None
    copay_collected_at: datetime | None = None
    copay_payment_method: str | None = None

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
