"""衛生局市民 — 首批 5 份專屬模組之一（09 §3.3：次數分級計價的代表）。

跟通用版的差異純粹是「導引」：把「這個人快用完了」「這期還有多少待核銷」
從數字堆裡挑出來，用一句話講給行政聽——資料完全來自 Layer 2 原語，這裡
不查新的東西，只是換一種呈現順序（09 §3.4 工具式 vs 導引式）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.institution.contracts.base import ContractModule
from app.institution.contracts.generic import build_generic_panel
from app.institution.models.contract import InstContract


class HealthBureauModule(ContractModule):
    def build_panel(self, db: Session, contract: InstContract) -> dict:
        panel = build_generic_panel(db, contract)
        panel["module"] = "health_bureau"

        alerts: list[str] = []
        for plan_panel in panel["plans"]:
            for e in plan_panel["enrollments"]:
                if e["quota_limit"] is not None and e["reserved"] == 1:
                    alerts.append(f"{e['case_name']} 只剩最後一次額度")
                if e["status"] == "exhausted" or (e["quota_limit"] is not None and e["reserved"] <= 0):
                    alerts.append(f"{e['case_name']} 額度已用罄")
            uncollected_count = len(plan_panel["claim_uncollected"])
            if uncollected_count > 0:
                total = sum((r["amount"] or 0) for r in plan_panel["claim_uncollected"])
                alerts.append(f"「{plan_panel['plan']['name']}」本期待核銷 {uncollected_count} 筆，共 ${total:,.0f}")

        panel["guidance"] = {"alerts": alerts}
        return panel
