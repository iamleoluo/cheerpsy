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

✅ list_per_case_count_candidates：grouping_mode="per_case_count" 的候選
   名單——依個案分組 list_uncollected() 的結果，標出誰已經達到容量門檻
   （09 §3.5 的 claim_by_count 區塊直接吃這個）。裝不滿也能送出（07 §4.3
   已定案），所以這支只是「標記」不是「擋下」。
✅ void_claim_case：作廢核銷案。內含紀錄一律脫離本案、payment_status
   退回 'unpaid'，可重新被收進新容器（09 §3.5 claim_list 區塊的作廢按鈕）。

尚未實作（TODO，留給下一輪）：
    - registered_hours 轉換（台南地院這類）尚未在 attach_records 自動套用，
      呼叫端需自行算好 actual_hours/registered_hours/registered_unit_price
      傳入。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.rules.numbering import next_claim_no
from app.models.case import Case
from app.models.session_record import SessionRecord
from app.models.user import User


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


def list_per_case_count_candidates(
    db: Session, claim_group_key: str, capacity: int, period_start: date | None = None, period_end: date | None = None
) -> list[dict]:
    """次數制核銷（09 §3.3 家防中心「每滿 N 次」代表這種模式）的候選名單。

    依個案分組 list_uncollected() 的結果，每組標出是否已達 capacity——但
    這只是提示，不是門檻：容器裝不滿也能送出（07 §4.3），行政要提前送
    一樣可以，只是這支查詢會告訴他「哪些人已經滿了、比較該優先處理」。
    """
    rows = list_uncollected(db, claim_group_key, period_start, period_end)
    by_case: dict[int, list[SessionRecord]] = {}
    for r in rows:
        by_case.setdefault(r.case_id, []).append(r)
    return [
        {
            "case_id": case_id,
            "session_record_ids": [r.id for r in recs],
            "count": len(recs),
            "ready": len(recs) >= capacity,
            "total_amount": sum((r.institution_payable or r.amount) for r in recs),
        }
        for case_id, recs in by_case.items()
    ]


def void_claim_case(db: Session, claim_case_id: int, reason: str | None, voided_by: int | None = None) -> InstClaimCase:
    """作廢核銷案（任一階段皆可，07 §4.3 核銷案流程的回頭路）。

    內含紀錄一律脫離本案：刪掉 inst_claim_lines（不是留著標記，因為
    「脫離」就是要讓它重新出現在 list_uncollected() 裡，而那支查詢本來
    就是用「有沒有被任何 line 收納」判斷，line 還在就會被排除）；
    payment_status 退回 'unpaid'，可被收進新核銷案。
    """
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")
    if cc.status == "void":
        raise ValueError("此核銷案已經是作廢狀態")
    for line in list(cc.lines):
        sr = db.query(SessionRecord).filter(SessionRecord.id == line.session_record_id).first()
        if sr is not None:
            sr.payment_status = "unpaid"
        db.delete(line)
    cc.status = "void"
    cc.voided_at = datetime.now(timezone.utc)
    cc.voided_reason = reason
    db.flush()
    return cc


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


def waive_docs(db: Session, claim_case_id: int, user_id: int) -> int:
    """文件豁免（從舊 claim_batches 移植，見 services/claim_batch.py 的
    apply_doc_waiver）。免繳文件的機構，行政一鍵把容器內所有「心理師還沒
    提交」的紀錄標記成視同已提交——不動 admin_verified_at，行政核對這一步
    仍然要做（豁免的是心理師那一關，不是行政核對那一關）。回傳影響筆數。
    """
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")
    now = datetime.now(timezone.utc)
    sr_ids = [line.session_record_id for line in cc.lines]
    recs = (
        db.query(SessionRecord)
        .filter(SessionRecord.id.in_(sr_ids), SessionRecord.therapist_doc_submitted_at.is_(None))
        .all()
    )
    for r in recs:
        r.therapist_doc_submitted_at = now
        r.therapist_doc_submitted_by = user_id
    cc.docs_waived_at = now
    cc.docs_waived_by = user_id
    db.flush()
    return len(recs)


def unwaive_docs(db: Session, claim_case_id: int) -> int:
    """撤銷豁免：只還原「被這次豁免動作自動確認」的紀錄（比對時間戳與操作
    人），真正由心理師自己提交的不會被誤還原。見 services/claim_batch.py
    的 revert_doc_waiver。回傳影響筆數。
    """
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")
    if cc.docs_waived_at is None:
        return 0
    sr_ids = [line.session_record_id for line in cc.lines]
    recs = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.id.in_(sr_ids),
            SessionRecord.therapist_doc_submitted_at == cc.docs_waived_at,
            SessionRecord.therapist_doc_submitted_by == cc.docs_waived_by,
        )
        .all()
    )
    for r in recs:
        r.therapist_doc_submitted_at = None
        r.therapist_doc_submitted_by = None
    cc.docs_waived_at = None
    cc.docs_waived_by = None
    db.flush()
    return len(recs)


def build_claim_export_data(db: Session, claim_case_id: int) -> dict:
    """請款資料檢視（09 決策：不做 PDF 匯出，但核銷時要能一眼看到請款單
    需要的全部欄位，供行政複製貼上到各機構自己的 Word 格式）。不同機構的
    請款單格式差異很大，這裡不猜格式，只把「填任何格式都用得到」的欄位
    整理成一張表：個案、病歷號、日期、心理師、類型、自付額、請款額、
    外部代號（若方案要求）、登記時數（若方案有轉換規則）。
    """
    cc = db.query(InstClaimCase).filter(InstClaimCase.id == claim_case_id).first()
    if cc is None:
        raise ValueError(f"核銷案不存在：id={claim_case_id}")

    plans = db.query(InstPlan).filter(InstPlan.claim_group_key == cc.claim_group_key).all()
    plan_by_id = {p.id: p for p in plans}
    contract = plans[0].contract if plans else None

    lines = cc.lines
    sr_ids = [line.session_record_id for line in lines]
    records = {r.id: r for r in db.query(SessionRecord).filter(SessionRecord.id.in_(sr_ids)).all()}
    case_ids = {r.case_id for r in records.values() if r.case_id}
    cases = {c.id: c for c in db.query(Case).filter(Case.id.in_(case_ids)).all()}
    therapist_ids = {r.therapist_id for r in records.values()}
    therapists = {u.id: u for u in db.query(User).filter(User.id.in_(therapist_ids)).all()}
    enrollments = {
        e.case_id: e
        for e in db.query(InstEnrollment).filter(InstEnrollment.case_id.in_(case_ids), InstEnrollment.plan_id.in_(plan_by_id.keys())).all()
    }

    rows = []
    for line in lines:
        sr = records.get(line.session_record_id)
        if sr is None:
            continue
        case = cases.get(sr.case_id) if sr.case_id else None
        therapist = therapists.get(sr.therapist_id)
        enrollment = enrollments.get(sr.case_id) if sr.case_id else None
        rows.append({
            "session_record_id": sr.id,
            "case_name": case.name if case else None,
            "case_number": case.case_number if case else None,
            "external_case_code": enrollment.external_case_code if enrollment else None,
            "session_date": sr.session_date,
            "therapist_name": therapist.name if therapist else None,
            "session_type": sr.session_type,
            "case_payable": sr.case_payable,
            "claimed_amount": line.claimed_amount,
            "actual_hours": line.actual_hours,
            "registered_hours": line.registered_hours,
            "registered_unit_price": line.registered_unit_price,
        })
    rows.sort(key=lambda r: (r["case_name"] or "", r["session_date"]))

    return {
        "claim_no": cc.claim_no,
        "claim_group_key": cc.claim_group_key,
        "status": cc.status,
        "period_start": cc.period_start,
        "period_end": cc.period_end,
        "institution_name": contract.institution.name if contract and contract.institution else None,
        "contract_name": contract.name if contract else None,
        "plan_names": [p.name for p in plans],
        "total_amount": sum((r["claimed_amount"] or Decimal("0")) for r in rows),
        "record_count": len(rows),
        "rows": rows,
    }
