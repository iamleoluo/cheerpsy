"""機構應收的跨機構唯讀檢視 — V2升級計畫 09 §4.2。

應收帳冊的第三個分頁。前兩個分頁（未收／月結）講的是**個案自己要付的錢**，
這一頁講的是完全另一段：**機構要撥給診所的那一段**（institution_payable）。

09 §1.4a 把這條界線講得很清楚：

    自付款流程   每天都要看到 —— 報到收款、日報表、應收帳冊未收/月結
    機構請款流程 主動點開才看到 —— 合約專頁的核銷分頁

所以這一頁是**唯讀**的（09 §4.2）：收款動作一律回合約專頁執行，避免同一筆錢
有兩個地方可以按「已收到款項」、狀態打架。

這頁要回答的是「機構那邊還有多少錢沒進來」，而那是兩段不同的錢：

    ① 已送出、等撥款   已經開單請款了，在等對方付
    ② 尚未收納         做完了但還沒被任何核銷案撈進去 —— 也就是還沒請款

第 ② 段特別重要：那是**還沒開始要錢**的錢。07 §4.3 建議把它做成常駐檢視，
因為「有沒有錢忘了收」是行政最容易漏的一件事，而它在合約專頁裡是分散在
各個合約底下的，跨機構看不到全貌。
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.models.institution import Institution
from app.models.session_record import SessionRecord

# 送出後超過這麼久還沒入帳，值得追一下
OVERDUE_DAYS = 45


def _institution_by_group_key(db: Session) -> dict[str, str]:
    """claim_group_key → 機構名。

    容器只存 group_key（國軍-個別／講座／團輔三個方案共用一個），行政看 key
    認不出是哪一家。
    """
    out: dict[str, str] = {}
    for key, inst_name in (
        db.query(InstPlan.claim_group_key, Institution.name)
        .join(InstContract, InstContract.id == InstPlan.contract_id)
        .join(Institution, Institution.id == InstContract.institution_id)
        .filter(InstPlan.claim_group_key.isnot(None))
        .all()
    ):
        out.setdefault(key, inst_name)
    return out


def institution_receivable(db: Session, today: date | None = None) -> dict:
    """機構應收全貌。純讀取，不寫任何資料。"""
    today = today or date.today()
    names = _institution_by_group_key(db)

    # ── ① 已送出、等撥款 ────────────────────────────────────────────────
    awaiting = []
    for c in (
        db.query(InstClaimCase)
        .filter(InstClaimCase.status == "submitted", InstClaimCase.voided_at.is_(None))
        .order_by(InstClaimCase.claim_no)
        .all()
    ):
        # 沒有 submitted_at 欄位，用建立日估算等待天數（狀態機是單向的，
        # 容器一旦 submitted 就不會回頭，所以這個估算不會誤差太大）
        since = c.created_at.date() if c.created_at else None
        days = (today - since).days if since else None
        awaiting.append(
            {
                "claim_case_id": c.id,
                "claim_no": c.claim_no,
                "claim_group_key": c.claim_group_key,
                "institution_name": names.get(c.claim_group_key),
                "period_start": c.period_start,
                "period_end": c.period_end,
                "record_count": len(c.lines),
                "applied_amount": float(c.applied_amount or 0),
                "waiting_days": days,
                "is_overdue": bool(days is not None and days > OVERDUE_DAYS),
            }
        )

    # ── ② 尚未收納：做完了但沒被任何核銷案撈進去 ────────────────────────
    claimed_ids = {row[0] for row in db.query(InstClaimLine.session_record_id).all()}
    by_plan: dict[int | None, dict] = {}
    for rec in (
        db.query(SessionRecord)
        .filter(
            SessionRecord.funding_source == "institution",
            SessionRecord.is_void.is_(False),
            func.coalesce(SessionRecord.institution_payable, 0) > 0,
        )
        .all()
    ):
        # 「已收納」是另一張表的全集合，只能在這裡排除
        if rec.id in claimed_ids:
            continue
        b = by_plan.setdefault(
            rec.plan_id,
            {"plan_id": rec.plan_id, "count": 0, "amount": 0.0, "oldest": None, "newest": None},
        )
        b["count"] += 1
        b["amount"] += float(rec.institution_payable or 0)
        b["oldest"] = rec.session_date if b["oldest"] is None else min(b["oldest"], rec.session_date)
        b["newest"] = rec.session_date if b["newest"] is None else max(b["newest"], rec.session_date)

    plan_meta = {
        p.id: (p.name, p.claim_group_key)
        for p in db.query(InstPlan).filter(InstPlan.id.in_([k for k in by_plan if k])).all()
    }
    uncollected = []
    for plan_id, b in by_plan.items():
        plan_name, group_key = plan_meta.get(plan_id, (None, None))
        uncollected.append(
            {
                **b,
                "plan_name": plan_name,
                "claim_group_key": group_key,
                "institution_name": names.get(group_key or ""),
                # 跨月遺留：最舊那筆已經是上個月以前的，代表漏掉了（07 §4.3）
                "is_stale": bool(
                    b["oldest"] and (b["oldest"].year, b["oldest"].month) < (today.year, today.month)
                ),
            }
        )
    uncollected.sort(key=lambda x: (not x["is_stale"], -x["amount"]))

    awaiting_total = sum(a["applied_amount"] for a in awaiting)
    uncollected_total = sum(u["amount"] for u in uncollected)
    return {
        "as_of": today,
        "awaiting_payment": awaiting,
        "uncollected": uncollected,
        "summary": {
            "awaiting_count": len(awaiting),
            "awaiting_total": awaiting_total,
            "awaiting_overdue": sum(1 for a in awaiting if a["is_overdue"]),
            "uncollected_count": sum(u["count"] for u in uncollected),
            "uncollected_total": uncollected_total,
            "uncollected_stale": sum(1 for u in uncollected if u["is_stale"]),
            "total": awaiting_total + uncollected_total,
        },
    }
