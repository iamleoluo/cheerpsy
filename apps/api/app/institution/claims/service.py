"""Layer 3・核銷案容器的操作。見 07 §4.3（2026/09/07 容器模型，已定案）。

這裡的函式不屬於 funding.ports.FundingPlanProvider——容器是核銷案管理頁
（行政操作，跟單筆預約的生命週期無關）用的，所以獨立成自己的 service，
由 app/institution/routers/admin.py 呼叫。

已實作（誠實標記，供下一輪擴充參考）：
    ✅ list_uncollected：找出「機構應收但還沒被任何容器收納」的紀錄——
       這是送出前漏單提醒、跨月遺留提醒共用的同一個查詢（07 §4.3 note）。
    ✅ open_claim_case：開一個空容器。
    ✅ attach_records：手動把指定的 session_record 塞進容器。
    ✅ submit：送出容器（不要求裝滿），把裡面所有紀錄的 payment_status
       推進 'claiming'（機構應收款／待核銷中）。
    ✅ record_payment：入帳，把紀錄推進 'claimed'，容器鎖定。

尚未實作（TODO，留給下一輪）：
    - 依 grouping_mode="per_case_count" 自動把「某個案累積滿 N 次」的紀錄
      自動收進容器——目前 attach_records 需要行政或程式呼叫端自己算出
      候選 session_record_ids。自動化版本要先確認「同一個案在同一方案
      裡，哪些紀錄還沒被任何容器收走」，邏輯與 list_uncollected 共用。
    - registered_hours 轉換（台南地院這類）尚未在 attach_records 自動套用，
      呼叫端需自行算好 actual_hours/registered_hours/registered_unit_price
      傳入。
    - inst_quota_pools 的總量扣減未串接（國軍 $149,000 那種池）。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.models.plan import InstPlan
from app.institution.rules.numbering import next_claim_no
from app.models.session_record import SessionRecord


def list_uncollected(
    db: Session, claim_group_key: str, period_start: date | None = None, period_end: date | None = None
) -> list[SessionRecord]:
    """機構應收、屬於此核銷群組、但還沒被任何 inst_claim_lines 收納的紀錄。

    用於：① 送出容器前的漏單提醒 ② 下月開容器時的跨月遺留提醒 ③ 行政隨時
    想確認「有沒有錢忘了收」的常駐檢視（07 §4.3 建議做成常駐頁面）。
    """
    plan_ids = [p.id for p in db.query(InstPlan.id).filter(InstPlan.claim_group_key == claim_group_key).all()]
    if not plan_ids:
        return []
    already_claimed_ids = {row[0] for row in db.query(InstClaimLine.session_record_id).all()}
    q = db.query(SessionRecord).filter(
        SessionRecord.plan_id.in_(plan_ids),
        SessionRecord.funding_source == "institution",
        SessionRecord.is_void.is_(False),
    )
    if period_start:
        q = q.filter(SessionRecord.session_date >= period_start)
    if period_end:
        q = q.filter(SessionRecord.session_date <= period_end)
    return [r for r in q.all() if r.id not in already_claimed_ids]


def open_claim_case(
    db: Session,
    claim_group_key: str,
    grouping_mode: str = "period",
    capacity: int | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    created_by: int | None = None,
) -> InstClaimCase:
    """開一個空容器。行政隨時可開（08 決策：不需要等月底、不需要裝滿）。"""
    cc = InstClaimCase(
        claim_no=next_claim_no(db),
        claim_group_key=claim_group_key,
        grouping_mode=grouping_mode,
        capacity=capacity,
        period_start=period_start,
        period_end=period_end,
        status="collecting",
        created_by=created_by,
    )
    db.add(cc)
    db.flush()
    return cc


def attach_records(
    db: Session, claim_case_id: int, session_record_ids: list[int], registered_hours_overrides: dict[int, dict] | None = None
) -> list[InstClaimLine]:
    """把指定的 session_record 塞進容器。裝不滿也沒關係——門檻是容量上限，不是阻擋條件。"""
    overrides = registered_hours_overrides or {}
    lines = []
    for sr_id in session_record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == sr_id).first()
        if sr is None:
            continue
        override = overrides.get(sr_id, {})
        line = InstClaimLine(
            claim_case_id=claim_case_id,
            session_record_id=sr_id,
            claimed_amount=sr.institution_payable if sr.institution_payable is not None else sr.amount,
            actual_hours=override.get("actual_hours"),
            registered_hours=override.get("registered_hours"),
            registered_unit_price=override.get("registered_unit_price"),
        )
        db.add(line)
        lines.append(line)
    db.flush()
    return lines


def submit(db: Session, claim_case_id: int) -> InstClaimCase:
    """送出容器——不要求裝滿。把容器內每筆紀錄的 payment_status 推進 'claiming'。

    收入認列不受影響：session_records.session_date（執行月）從頭到尾不變，
    這裡只動 payment_status，對應「機構應收款／待核銷中」的中間狀態（見 07 §4.3）。
    """
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")
    total = Decimal("0")
    for line in cc.lines:
        sr = db.query(SessionRecord).filter(SessionRecord.id == line.session_record_id).first()
        if sr is not None:
            sr.payment_status = "claiming"
        total += line.claimed_amount or Decimal("0")
    cc.applied_amount = total
    cc.status = "submitted"
    db.flush()
    return cc


def record_payment(
    db: Session,
    claim_case_id: int,
    received_date: date,
    received_amount: Decimal,
    income_tax_amount: Decimal = Decimal("0"),
    transfer_fee: Decimal = Decimal("0"),
) -> InstClaimCase:
    """入帳。收入仍掛在原執行月（不搬月），這裡只沖銷應收、鎖定容器。"""
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")
    for line in cc.lines:
        sr = db.query(SessionRecord).filter(SessionRecord.id == line.session_record_id).first()
        if sr is not None:
            sr.payment_status = "claimed"
    cc.received_date = received_date
    cc.received_amount = received_amount
    cc.income_tax_amount = income_tax_amount
    cc.transfer_fee = transfer_fee
    cc.net_received = received_amount - income_tax_amount - transfer_fee
    cc.status = "closed"
    cc.locked_at = datetime.now(timezone.utc)
    db.flush()
    return cc
