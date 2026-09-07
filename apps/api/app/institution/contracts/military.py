"""國軍心理照護方案 — 首批 5 份專屬模組之一（09 §3.3：合約層級金額池的代表）。

池子是這份合約的核心資產，通用版只把它當成方案底下的一個區塊；這裡把它
拉到最前面當headline，並在池子快見底時主動示警——這正是「導引式」跟
「工具式」的差別（09 §3.4）：通用版要行政自己盯著數字，這裡系統先講。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.institution.contracts.base import ContractModule
from app.institution.contracts.generic import build_generic_panel
from app.institution.models.contract import InstContract

LOW_REMAINING_RATIO = Decimal("0.15")  # 剩餘低於總額 15% 時示警，可視實際使用經驗調整


class MilitaryModule(ContractModule):
    def build_panel(self, db: Session, contract: InstContract) -> dict:
        panel = build_generic_panel(db, contract)
        panel["module"] = "military"

        alerts: list[str] = []
        pool_summary = None
        for plan_panel in panel["plans"]:
            pool = plan_panel["quota_pool"]
            if pool is None:
                continue
            pool_summary = pool
            if pool["total_limit"] is not None:
                total = Decimal(str(pool["total_limit"]))
                remaining = Decimal(str(pool["remaining"])) if pool["remaining"] is not None else Decimal("0")
                if total > 0 and remaining / total <= LOW_REMAINING_RATIO:
                    unit = "$" if pool["unit"] == "amount" else ""
                    alerts.append(f"「{pool['name']}」即將用罄，剩餘 {unit}{remaining:,.0f}（總額 {unit}{total:,.0f} 的 {remaining / total:.0%}）")
            uncollected_count = len(plan_panel["claim_uncollected"])
            if uncollected_count > 0:
                total_amt = sum((r["amount"] or 0) for r in plan_panel["claim_uncollected"])
                alerts.append(f"「{plan_panel['plan']['name']}」本期待核銷 {uncollected_count} 筆，共 ${total_amt:,.0f}")

        panel["guidance"] = {"alerts": alerts, "headline_pool": pool_summary}
        return panel
