"""註冊槽：main.py 啟動時把子系統的 provider 塞進來；呼叫端一律透過
get_provider() 拿實例，不直接 import 子系統。

預設是 NullProvider——代表「沒有任何外部給付方」，行為等同純自費診所。
這讓主系統可以在完全不知道機構子系統存在的情況下被測試、被 import。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.funding.dto import EnrollmentState, PlanOption, Quote, QuoteRequest
from app.funding.ports import FundingPlanProvider


class NullProvider:
    """沒有註冊任何 provider 時的預設實作。純自費診所可以完全不碰這一塊。"""

    def list_eligible_plans(
        self, db: Session, case_id: int, on_date: date, session_type: str | None = None
    ) -> list[PlanOption]:
        return []

    def quote(self, db: Session, request: QuoteRequest) -> Quote:
        raise LookupError(
            f"No FundingPlanProvider registered — cannot quote plan_id={request.plan_id}. "
            "若要啟用機構方案，於 app/main.py 呼叫 "
            "funding_registry.register(InstitutionFundingProvider())。"
        )

    def get_case_enrollments(self, db: Session, case_id: int) -> list[EnrollmentState]:
        return []

    def enroll(self, db: Session, case_id: int, plan_id: int, external_case_code=None, **kwargs):
        raise LookupError("No FundingPlanProvider registered.")

    def reserve(self, db: Session, appointment_id: int, quote: Quote) -> None:
        raise LookupError("No FundingPlanProvider registered.")

    def consume(self, db: Session, appointment_id: int) -> None:
        raise LookupError("No FundingPlanProvider registered.")

    def release(self, db: Session, appointment_id: int, reason: str) -> None:
        raise LookupError("No FundingPlanProvider registered.")

    def close_case_enrollments(self, db: Session, case_id: int) -> None:
        return None


_provider: FundingPlanProvider = NullProvider()


def register(provider: FundingPlanProvider) -> None:
    """在 app.main 啟動時呼叫一次。"""
    global _provider
    _provider = provider


def get_provider() -> FundingPlanProvider:
    return _provider


def has_provider() -> bool:
    return not isinstance(_provider, NullProvider)
