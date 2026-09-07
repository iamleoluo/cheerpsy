"""鉅微借場地 — 首批 5 份專屬模組之一
（09 §3.3：無心理師勞務、不計額度的代表）。

compensation_mode=none、counts_toward_quota=false：沒有心理師抽成、
沒有個人額度三態這件事。通用版仍然會跑出一個「quota_unlimited」區塊
（因為方案沒設上限），但那個區塊對這種合約沒有意義——這裡直接拿掉，
換成單純的場次與場地費清單，行政看的是「這個月借了幾次、多少場地費」，
不是額度使用情形。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.institution.contracts.base import ContractModule
from app.institution.contracts.generic import build_generic_panel
from app.institution.models.contract import InstContract


class VenueRentalModule(ContractModule):
    def build_panel(self, db: Session, contract: InstContract) -> dict:
        panel = build_generic_panel(db, contract)
        panel["module"] = "venue_rental"

        for plan_panel in panel["plans"]:
            # 這種合約沒有個人額度概念，quota_unlimited 區塊對它沒有意義，
            # 拿掉後前端就不會畫出一個空空的額度區塊。
            plan_panel["blocks"] = [b for b in plan_panel["blocks"] if b != "quota_unlimited"]

        total_sessions = sum(len(p["claim_uncollected"]) for p in panel["plans"])
        total_amount = sum(sum((r["amount"] or 0) for r in p["claim_uncollected"]) for p in panel["plans"])
        panel["guidance"] = {
            "venue_summary": {"pending_sessions": total_sessions, "pending_amount": total_amount},
            "note": "借場地：無心理師勞務、不計個人額度，這裡只追蹤場次與場地費，不顯示額度使用情形。",
        }
        return panel
