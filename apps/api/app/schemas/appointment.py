from datetime import datetime

from pydantic import BaseModel, Field

# 「金額」只是預約上的一個數字（顯示在 Google 日曆事件標題），不是記帳：沒有收款、結算、額度、分潤。
# 隔離的單位是心理師，不是欄位：心理師對自己的預約有完整權限（含金額），行政對全部；0＝沒有金額。
# 機構方案、額度、付款方式屬「金流資訊」，已恢復：funding_source（self_pay／institution，沒送就沿用個案設定）、
# quota_id（沒送就自動挑）。額度不足只回 warnings，不擋預約。
Amount = Field(None, ge=0, le=9_999_999)


class AppointmentCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    start_time: datetime
    end_time: datetime
    amount: float | None = Amount  # 自費：必填（個案要付的全額）；機構：不送＝由方案價目帶出，送了＝行政手動調整
    funding_source: str | None = None  # self_pay | institution；沒送＝沿用個案的付款方式
    quota_id: int | None = None  # 機構案指定額度；沒送＝自動挑
    plan_id: int | None = None  # 機構案的方案；沒送＝用額度所屬方案
    rate_item_id: int | None = None  # 價目項目；沒送＝依方案、時長、第幾次自動挑
    transport_fee_option_id: int | None = None  # 交通費選項；沒送＝現場無交通費、外出用預設選項
    couple_case_id: int | None = None  # 合療：標記場次所屬伴侶案（case_id 為付款方）


class BatchSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    amount: float | None = None  # 已忽略（整批用最上層的 amount）
    funding_source: str | None = None  # 已忽略（整批用最上層的設定）
    quota_id: int | None = None  # 已忽略


class AppointmentBatchCreate(BaseModel):
    case_id: int
    room_id: int | None = None
    session_type: str = "in_person"
    amount: float | None = Amount  # 選填；整批每一場同一個金額（slot 上的 amount 已忽略）
    funding_source: str | None = None
    quota_id: int | None = None
    plan_id: int | None = None
    rate_item_id: int | None = None
    transport_fee_option_id: int | None = None
    couple_case_id: int | None = None
    slots: list[BatchSlot]


class AppointmentUpdate(BaseModel):
    room_id: int | None = None
    session_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    amount: float | None = Amount  # 不送＝不改；送了＝手動調整應收（機構案會寫稽核）
    # 改方案、價目項目、交通費時，會依 plan_pricing 重新計算應收與自付額（改價目主檔不影響既有預約）
    plan_id: int | None = None
    rate_item_id: int | None = None
    transport_fee_option_id: int | None = None


PAYMENT_METHODS = ("cash", "transfer", "card", "other")


class AppointmentCollectionUpdate(BaseModel):
    """收款記錄：只記狀態、方式、時間、經手人（時間與經手人由伺服器填）。"""

    payment_status: str  # unpaid 未收 | paid 已收 | waived 免收
    payment_method: str | None = None  # cash 現金 | transfer 轉帳 | card 刷卡 | other 其他；已收必填


class AppointmentPaymentUpdate(BaseModel):
    funding_source: str  # self_pay | institution
    quota_id: int | None = None
    plan_id: int | None = None
    rate_item_id: int | None = None
    transport_fee_option_id: int | None = None
    amount: float | None = Amount  # 自費必填；機構不送＝由價目帶出


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
    # amount：真實金額（0＝沒有金額）。行政看全部、心理師看自己的；會計維持 0。
    amount: float = 0
    funding_source: str | None = None  # self_pay | institution
    quota_id: int | None = None
    quota_institution_name: str | None = None
    # 提示（不擋預約）：額度不足、已過期、沒有額度等
    warnings: list[str] = []
    therapist_share: float | None = None
    clinic_share: float | None = None
    visit_seq: int | None = None
    status: str
    batch_id: str | None = None
    created_at: datetime | None = None
    # Phase 3
    checkin_status: str = "pending"   # pending 待報到／arrived 已到／absent 未到
    checked_in_at: datetime | None = None
    no_show_type: str | None = None
    no_show_fee: float = 0
    fee_item: str | None = None
    plan_id: int | None = None
    plan_name: str | None = None
    rate_item_id: int | None = None
    rate_item_label: str | None = None
    self_pay_amount: float = 0  # 個案這次要付的錢（自費＝全額；機構＝自付額）
    payment_status: str = "unpaid"  # unpaid 未收 | paid 已收 | waived 免收
    payment_method: str | None = None
    paid_at: datetime | None = None
    paid_by_name: str | None = None
    transport_fee_option_id: int | None = None
    transport_fee_label: str | None = None
    transport_fee: float = 0
    video_link: str | None = None
    notify_admin_to_forward: bool = False
    forwarded_at: datetime | None = None
    outreach_location: str | None = None
    hourly_rate: float | None = None
    is_intake: bool = False
    # 機構額度：只顯示總堂數、已用、剩餘（不擋預約）；最後一次 → 日曆方塊加紅框
    quota_is_last_session: bool = False
    quota_used: int | None = None
    quota_total: int | None = None
    quota_remaining: int | None = None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: int
    name: str
    floor: int
    room_code: str
    room_type: str = "talk"  # talk 晤談室／play 兒童遊戲室
    has_special_equipment: bool
    notes: str | None = None
    is_active: bool = True
    sort_order: int = 0

    model_config = {"from_attributes": True}
