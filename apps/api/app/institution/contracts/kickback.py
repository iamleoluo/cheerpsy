"""教支中心 — 首批 5 份專屬模組之一（09 §3.3：回饋制的代表）。

回饋制的金流方向跟其他合約相反：心理師直接向機構收款，事後回饋一部分
給診所——診所從沒收到這筆錢的全額，日報表也不該把它算進現金收入
（09 §1.2 已定案）。通用版的「個案與額度」分頁完全看不出這件事，這裡
額外做一張「心理師直接收款彙總」，把每位心理師收了多少、幾場，攤開來
給行政看，回饋金額則依各機構合約約定另計——目前資料庫沒有存回饋比例
這個欄位，所以不猜公式，只把原始數字備齊。
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.institution.contracts.base import ContractModule
from app.institution.contracts.generic import build_generic_panel
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.models.session_record import SessionRecord
from app.models.user import User


class KickbackModule(ContractModule):
    def build_panel(self, db: Session, contract: InstContract) -> dict:
        panel = build_generic_panel(db, contract)
        panel["module"] = "kickback"

        plan_ids = [p["plan"]["id"] for p in panel["plans"] if p["plan"]["compensation_mode"] == "kickback"]
        by_therapist: list[dict] = []
        if plan_ids:
            rows = (
                db.query(
                    SessionRecord.therapist_id,
                    func.count(SessionRecord.id).label("session_count"),
                    func.sum(SessionRecord.amount).label("total_amount"),
                )
                .filter(SessionRecord.plan_id.in_(plan_ids), SessionRecord.is_void.is_(False))
                .group_by(SessionRecord.therapist_id)
                .all()
            )
            therapists = {u.id: u.name for u in db.query(User).filter(User.id.in_([r.therapist_id for r in rows])).all()}
            by_therapist = [
                {
                    "therapist_id": r.therapist_id,
                    "therapist_name": therapists.get(r.therapist_id),
                    "session_count": r.session_count,
                    "total_collected": r.total_amount,
                }
                for r in rows
            ]

        panel["guidance"] = {
            "kickback_summary": by_therapist,
            "note": "回饋制：心理師直接向機構收款，此處是心理師自收總額，非診所收入；應回饋診所的金額請依合約約定另計。",
        }
        return panel
