"""主系統這一側定義的資料格式（DTO）。

這些型別是主系統與機構合約子系統溝通的唯一契約——刻意都是可序列化的
Pydantic model，不掛任何 SQLAlchemy model。子系統的 adapter 負責把自己的內部
資料組成這些型別；主系統只認得這些型別的欄位，不 import 子系統的 model。

對應 V2升級計畫 07_機構合約子系統架構.html §5.3（Quote 的完整 JSON 範例在那邊）。
這裡先實作一個「夠用、涵蓋文件描述的形狀」的版本；54 個方案的細節規則不會
反映在這支檔案裡，只會反映在 institution/ 內部的資料與邏輯。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PayerKind = Literal["case", "institution", "borrower"]
CompensationMode = Literal["commission", "kickback", "none"]
ClaimTiming = Literal["monthly", "quarterly", "semester", "threshold", "unscheduled"]
QuotaUnit = Literal["count", "amount"]
GroupingMode = Literal["per_case_count", "period"]


class Addon(BaseModel):
    """加給／附加費，例如交通費、深夜出勤加成。

    commissionable=False 的典型案例：脆家到宅的交通費不抽成、創造心生活的
    交通費不回扣。見 07 §1.1 模式⑦。
    """

    kind: str  # transport / late_night / other
    name: str
    amount: Decimal
    payer: PayerKind = "institution"
    commissionable: bool = True


class PricingResult(BaseModel):
    unit_price: Decimal  # 總鐘點費（含個案自付額）
    case_payable: Decimal = Decimal("0")
    institution_payable: Decimal = Decimal("0")
    addons: list[Addon] = Field(default_factory=list)


class ReceiptSpec(BaseModel):
    required: bool
    item_name: str | None = None


class ReceiptPlan(BaseModel):
    case: ReceiptSpec
    institution: ReceiptSpec


class QuotaBeforeState(BaseModel):
    used: int = 0
    booked: int = 0
    reserved: int = 0
    limit: int | None = None  # None = 不限


class QuotaEffect(BaseModel):
    consumes: bool  # False：此方案無額度概念（如借場地、部分外展方案）
    enrollment_id: int | None = None
    before: QuotaBeforeState = Field(default_factory=QuotaBeforeState)
    is_last: bool = False
    blocking: str | None = None  # 非 None 時代表額度不足／未評估通過等擋下原因


class CompensationPlan(BaseModel):
    mode: CompensationMode = "commission"
    commissionable_base: Decimal = Decimal("0")


class ClaimRouting(BaseModel):
    """核銷路由——主系統原封不動存著，自己不解讀，只在建立 session_record 時
    連同快照一起存進 plan_quote(JSONB)，供子系統之後建立/收納核銷案容器使用。
    """

    group_key: str
    timing: ClaimTiming = "monthly"
    deadline_day: int | None = None
    grouping_mode: GroupingMode = "period"
    capacity: int | None = None  # grouping_mode="per_case_count" 時的容器容量
    registered_hours_rule: dict | None = None  # 台南地院這類「登記時數≠實際時數」


class ChecklistPlan(BaseModel):
    admin: list[str] = Field(default_factory=list)
    therapist: list[str] = Field(default_factory=list)


class Quote(BaseModel):
    """報價快照——主系統收到後原封不動存進 appointments.plan_quote(JSONB)，
    並把 pricing/compensation/receipts 的攤平值另外寫進獨立欄位供 SUM 用。
    見 07 §4.2、§5.3。
    """

    quote_id: str
    plan_id: int
    plan_name: str
    plan_version: int = 1
    contract_id: int | None = None
    institution_name: str | None = None

    pricing: PricingResult
    receipts: ReceiptPlan
    quota: QuotaEffect
    compensation: CompensationPlan
    claim: ClaimRouting
    checklists: ChecklistPlan = Field(default_factory=ChecklistPlan)

    resolved_by: list[str] = Field(default_factory=list)  # 除錯用：命中了哪些規則
    valid_until: datetime | None = None


class PlanOption(BaseModel):
    """預約表單「方案」下拉的一列。"""

    plan_id: int
    plan_name: str
    institution_name: str | None = None
    quota_summary: str | None = None  # 例："青壯 2/3"
    is_last: bool = False
    disabled: bool = False
    disabled_reason: str | None = None


class EnrollmentState(BaseModel):
    """個案機構狀態列表的一列——個案詳情頁「機構方案」分頁直接渲染這個。"""

    enrollment_id: int
    plan_id: int
    plan_name: str
    institution_name: str | None = None
    external_case_code: str | None = None
    quota_unit: QuotaUnit = "count"
    quota_limit: Decimal | None = None
    used: Decimal = Decimal("0")
    booked: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")
    extended_count: int = 0
    valid_from: date | None = None
    valid_until: date | None = None
    assessment_status: Literal["not_required", "pending", "approved"] = "not_required"
    status: Literal["active", "exhausted", "expired", "closed"] = "active"


class QuoteRequest(BaseModel):
    """quote() 的輸入。"""

    case_id: int
    plan_id: int
    therapist_id: int
    session_type: str  # in_person / online / outdoor（沿用主系統既有枚舉）
    visit_seq: int | None = None
    duration_min: int = 60
    location_kind: str = "clinic"  # clinic / home / onsite / offsite
    appt_date: date | None = None
    sub_unit: str | None = None  # 蛹之生底下的台積電等子單位
