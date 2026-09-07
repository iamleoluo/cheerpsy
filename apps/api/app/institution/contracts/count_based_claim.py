"""市政府人事處（及同系列的教育局/環保局/消防局/文化局/民政局人事處，
見 seed_plans.py 註解） — 首批 5 份專屬模組之一
（09 §3.3：次數制核銷「每滿 N 次」的代表）。

通用版把「已達 N 次待核銷名單」放在核銷分頁裡一個平淡的區塊；這裡的
導引版把它拉到最前面當成這份合約的主要待辦——因為次數制核銷的行政
節奏跟期間制不一樣：不是「月底結一次」，而是「誰滿了就處理誰」，這份
名單本來就該是行政每次打開這份合約第一眼要看到的東西。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.institution.contracts.base import ContractModule
from app.institution.contracts.generic import build_generic_panel
from app.institution.models.contract import InstContract


class CountBasedClaimModule(ContractModule):
    def build_panel(self, db: Session, contract: InstContract) -> dict:
        panel = build_generic_panel(db, contract)
        panel["module"] = "count_based_claim"

        ready_to_claim: list[dict] = []
        in_progress: list[dict] = []
        for plan_panel in panel["plans"]:
            candidates = plan_panel["claim_candidates"]
            if not candidates:
                continue
            capacity = plan_panel["plan"]["claim_capacity"] or 0
            for c in candidates:
                row = {**c, "plan_name": plan_panel["plan"]["name"], "capacity": capacity}
                (ready_to_claim if c["ready"] else in_progress).append(row)

        panel["guidance"] = {
            "ready_to_claim": ready_to_claim,
            "in_progress": in_progress,
            "alerts": [f"{len(ready_to_claim)} 位個案已達核銷次數，可以開案" for _ in [0] if ready_to_claim],
        }
        return panel
