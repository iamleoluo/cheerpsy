"""主系統定義的「需求」——機構合約子系統要實作這個介面才能被接上。

★ 依賴方向規則（V2升級計畫 07 §3.2，已定案）★
    程式碼依賴只有一個方向：子系統 → 主系統。
    主系統的任何檔案（routers/、models/、services/）都不可以
    `import app.institution.*`——除了透過 app.funding.registry 拿到
    這裡定義的 Protocol 實例。

    驗收標準：把 app/institution/ 整包搬走，主系統的其餘程式碼要還能被
    import（雖然功能上會退化成「純自費診所」，因為沒有 provider 被註冊）。

    子系統那邊（app/institution/adapter.py）可以自由 import 主系統的
    models（Case、Appointment、SessionRecord...），因為依賴方向是允許的。

八支方法對應 07 §5.1／§5.2：前三支唯讀查詢，後五支有副作用、且必須由
呼叫端保證與其他寫入在同一個 DB 交易內一起 commit／rollback——這是選擇
「模組化單體＋依賴反轉」而非獨立微服務的主因（額度扣減不能有 saga）。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.funding.dto import EnrollmentState, PlanOption, Quote, QuoteRequest


@runtime_checkable
class FundingPlanProvider(Protocol):
    """一個「外部給付方報價引擎」的完整介面。

    目前唯一的實作是機構合約子系統（app.institution.adapter.InstitutionFundingProvider），
    但介面命名刻意不叫 InstitutionProvider——哪天出現保險給付、企業方案，
    那是再寫一個 adapter，這支介面與呼叫端都不用改。
    """

    # ---- 查詢類（無副作用） ----

    def list_eligible_plans(
        self, db: Session, case_id: int, on_date: date, session_type: str | None = None
    ) -> list[PlanOption]:
        """個案在指定日期、可選的諮商類型下，有哪些方案可選。用於預約表單下拉。"""
        ...

    def quote(self, db: Session, request: QuoteRequest) -> Quote:
        """核心：給一組情境條件，回傳完整報價快照。不寫入任何資料。"""
        ...

    def get_case_enrollments(self, db: Session, case_id: int) -> list[EnrollmentState]:
        """個案詳情頁「機構方案」分頁要顯示的完整狀態列表。純讀取，主系統不落地。"""
        ...

    # ---- 命令類（有副作用，需與呼叫端在同一交易內） ----

    def enroll(
        self, db: Session, case_id: int, plan_id: int, external_case_code: str | None = None, **kwargs
    ) -> EnrollmentState:
        """個案加入方案。額度上限全數進「已預留」。"""
        ...

    def reserve(self, db: Session, appointment_id: int, quote: Quote) -> None:
        """建立預約時呼叫。若 quote.quota.consumes，把對應 enrollment 的
        已預留 -1（轉為已預約，已預約本身不落地，用 status='booked' 的
        appointment 數量查詢時算）。"""
        ...

    def consume(self, db: Session, appointment_id: int) -> None:
        """報到按「已到」時呼叫。已預約 → 已使用。

        前置檢查（見 07 §8.3）：呼叫端必須確保該預約對應的個案已有正式病歷號
        （cases.case_number IS NOT NULL）——這裡不重複檢查身分階段，只管額度轉移。
        """
        ...

    def unconsume(self, db: Session, appointment_id: int) -> None:
        """帳冊紀錄作廢時呼叫。已使用 → 已預留，並退回合約層級額度池。

        與核銷作廢無關：核銷作廢代表「不跟機構請款」，場次仍成立、額度照扣。
        """
        ...

    def release(
        self, db: Session, appointment_id: int, reason: str, *, bill_no_show_fee: bool = True
    ) -> None:
        """未到／取消／個案請假時呼叫。已預約 → 已預留（不是釋回，個案仍保有額度）。

        機構未到補助（09 §7.1 已裁示）：若該預約掛的方案有設定
        no_show_fee_numeric，這裡也會順便產生一筆機構請款紀錄（不消耗個
        人額度）——呼叫端不需要另外處理，這是子系統內部決定要不要做的事。

        `bill_no_show_fee=False` 用在「額度要還、但不該收未到補助」的情境：
        取消預約與個案請假都算這一類（機構補助的是「個案沒出現」，不是
        「這場沒發生」）。用明確參數而不是去解析 reason 字串，是因為 reason
        是自由文字，打錯字會靜默地變成多收一筆機構的錢。
        """
        ...

    def close_case_enrollments(self, db: Session, case_id: int) -> None:
        """個案結案時呼叫。該個案在所有方案的已預留＋已預約全數歸零。"""
        ...
