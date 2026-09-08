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

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.rules.numbering import next_claim_no
from app.models.case import Case
from app.models.notification import Notification
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit


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


def parse_registered_hours_rule(raw: str | None) -> dict | None:
    """登記時數轉換規則。台南地院那種「1 實際小時 → 登記 2 小時 @$800」。

    改成宣告式 JSON：{"multiplier": 2, "registered_unit_price": 800}
    ——原本這欄是給人看的自由文字，要套用只能靠行政自己心算再手動填。
    刻意不做中文字串剖析：規則本來就該用結構化的方式寫，寫個 parser 去猜
    「1hr實際→2hr@$800」這種句子，是把資料建檔的問題丟給程式碼扛。
    看不懂的內容一律回 None（當成沒有規則），舊的自由文字備忘不會壞掉。
    """
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    mult = data.get("multiplier")
    price = data.get("registered_unit_price")
    if mult is None and price is None:
        return None
    return {
        "multiplier": Decimal(str(mult)) if mult is not None else Decimal("1"),
        "registered_unit_price": Decimal(str(price)) if price is not None else None,
    }


def check_external_codes(db: Session, session_record_ids: list[int]) -> list[dict]:
    """收納前檢查：方案要求個案代號（requires_external_code）的，個案必須
    已經拿到機構給的代號，否則送出去機構會退件。

    07 §8.3 把這件事列為收納時的擋下條件，adapter.py:479 也留了 TODO。
    回傳缺代號的清單，由呼叫端決定要擋還是只提醒。
    """
    missing = []
    for sr_id in session_record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == sr_id).first()
        if sr is None or sr.plan_id is None:
            continue
        plan = db.query(InstPlan).filter(InstPlan.id == sr.plan_id).first()
        if plan is None or not plan.requires_external_code:
            continue
        e = (
            db.query(InstEnrollment)
            .filter(InstEnrollment.case_id == sr.case_id, InstEnrollment.plan_id == sr.plan_id)
            .first()
        )
        if e is None or not (e.external_case_code or "").strip():
            case = db.query(Case).filter(Case.id == sr.case_id).first()
            missing.append({
                "session_record_id": sr_id,
                "case_id": sr.case_id,
                "case_name": case.name if case else None,
                "plan_name": plan.name,
            })
    return missing


def attach_records(
    db: Session,
    claim_case_id: int,
    session_record_ids: list[int],
    registered_hours_overrides: dict[int, dict] | None = None,
    enforce_external_code: bool = True,
) -> list[InstClaimLine]:
    """把指定的 session_record 塞進容器。裝不滿也沒關係——門檻是容量上限，不是阻擋條件。

    兩件收納時才做得了的事：
      ① 個案代號檢查（07 §8.3）——缺代號送出去機構會退件，在這裡擋比較便宜。
      ② 登記時數轉換——依方案的 registered_hours_rule 換算申請金額。
         呼叫端仍可用 overrides 手動指定，覆蓋自動換算的結果。
    """
    if enforce_external_code:
        missing = check_external_codes(db, session_record_ids)
        if missing:
            names = "、".join(f"{m['case_name']}（{m['plan_name']}）" for m in missing[:5])
            raise ValueError(f"以下個案尚未填寫機構個案代號，無法收納：{names}")

    overrides = registered_hours_overrides or {}
    lines = []
    for sr_id in session_record_ids:
        sr = db.query(SessionRecord).filter(SessionRecord.id == sr_id).first()
        if sr is None:
            continue
        override = overrides.get(sr_id, {})
        claimed = sr.institution_payable if sr.institution_payable is not None else sr.amount
        actual_hours = override.get("actual_hours")
        registered_hours = override.get("registered_hours")
        registered_unit_price = override.get("registered_unit_price")

        if registered_hours is None and sr.plan_id is not None:
            plan = db.query(InstPlan).filter(InstPlan.id == sr.plan_id).first()
            rule = parse_registered_hours_rule(plan.registered_hours_rule if plan else None)
            if rule is not None:
                actual_hours = actual_hours or _actual_hours_of(db, sr)
                registered_hours = (actual_hours * rule["multiplier"]).quantize(Decimal("0.01"))
                registered_unit_price = rule["registered_unit_price"]
                if registered_unit_price is not None:
                    claimed = (registered_hours * registered_unit_price).quantize(Decimal("1"))

        line = InstClaimLine(
            claim_case_id=claim_case_id,
            session_record_id=sr_id,
            claimed_amount=claimed,
            actual_hours=actual_hours,
            registered_hours=registered_hours,
            registered_unit_price=registered_unit_price,
        )
        db.add(line)
        lines.append(line)
    db.flush()
    return lines


def _actual_hours_of(db: Session, sr: SessionRecord) -> Decimal:
    """場次實際時數。有預約就用預約長度（加時後已回寫），沒有就當 1 小時。"""
    from app.models.appointment import Appointment

    if sr.appointment_id:
        appt = db.query(Appointment).filter(Appointment.id == sr.appointment_id).first()
        if appt and appt.time_range and appt.time_range.upper and appt.time_range.lower:
            minutes = (appt.time_range.upper - appt.time_range.lower).total_seconds() / 60
            return (Decimal(str(minutes)) / Decimal("60")).quantize(Decimal("0.01"))
    return Decimal("1")


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


# ─────────────────────────────────────────────────────────────────────────
# 期間缺口／重疊警告（v7 核銷案 §建立核銷案三步驟）
# ─────────────────────────────────────────────────────────────────────────

def check_period_coverage(
    db: Session, claim_group_key: str, period_start: date, period_end: date,
    exclude_claim_case_id: int | None = None,
) -> dict:
    """建立核銷案時，比對同一群組先前的期間，找出缺口與重疊。

    v7 定案：**警告不阻擋**。行政比系統更清楚為什麼這段要跳過（例如那個月
    根本沒開案、或前一案已經補送過），所以這裡只負責把事實攤開來講，
    要不要繼續由人決定。

      缺口 → 「X 天未被納入，可能漏請款」
      重疊 → 「與核銷案 YYYYMM-NN 重疊 X 天，恐重複請款」
    """
    q = db.query(InstClaimCase).filter(
        InstClaimCase.claim_group_key == claim_group_key,
        InstClaimCase.status != "void",
        InstClaimCase.period_start.isnot(None),
        InstClaimCase.period_end.isnot(None),
    )
    if exclude_claim_case_id:
        q = q.filter(InstClaimCase.id != exclude_claim_case_id)
    previous = q.order_by(InstClaimCase.period_end.desc()).all()

    warnings: list[dict] = []

    overlaps = [c for c in previous if c.period_start <= period_end and c.period_end >= period_start]
    for c in overlaps:
        days = (min(period_end, c.period_end) - max(period_start, c.period_start)).days + 1
        warnings.append({
            "kind": "overlap",
            "claim_no": c.claim_no,
            "days": days,
            "message": f"與核銷案 {c.claim_no}（{c.period_start}~{c.period_end}）重疊 {days} 天，恐重複請款",
        })

    last_before = next((c for c in previous if c.period_end < period_start), None)
    if last_before is not None:
        gap = (period_start - last_before.period_end).days - 1
        if gap > 0:
            warnings.append({
                "kind": "gap",
                "claim_no": last_before.claim_no,
                "days": gap,
                "message": f"上一個核銷案結束於 {last_before.period_end}，中間有 {gap} 天未被納入，可能漏請款",
            })

    uncollected = list_uncollected(db, claim_group_key, period_end=period_start - timedelta(days=1))
    if uncollected:
        total = sum(float(r.institution_payable or r.amount) for r in uncollected)
        warnings.append({
            "kind": "leftover",
            "claim_no": None,
            "days": 0,
            "message": f"本期之前尚有 {len(uncollected)} 筆未收納（共 ${total:,.0f}），"
                       f"最早 {min(r.session_date for r in uncollected)}",
        })

    return {
        "suggested_start": (last_before.period_end + timedelta(days=1)) if last_before else None,
        "last_period_end": last_before.period_end if last_before else None,
        "warnings": warnings,
        "blocking": False,   # v7 定案：一律警告不阻擋
    }


# ─────────────────────────────────────────────────────────────────────────
# 退回補件（v7 核銷案 §資料齊備的三條路）
# ─────────────────────────────────────────────────────────────────────────

def return_for_correction(
    db: Session, session_record_id: int, reason: str, actor_id: int | None = None
) -> SessionRecord:
    """行政發現某一筆文件有問題 → 退回補件。

    v7 明訂要**同時清除心理師確認與行政核對**兩個閘門，把那一筆打回「待提交」
    並通知心理師。原本系統只有 admin-unverify（清行政那一側、沒有原因、
    也不通知），心理師端根本看不到自己被退件了，那一筆就會卡在那裡。

    這是**單筆**操作，不影響同案其他紀錄；但只要有一筆沒齊備，整案就無法
    轉「待送出」——那個判斷在 check_readiness()／submit() 端。
    """
    sr = db.query(SessionRecord).filter(SessionRecord.id == session_record_id).first()
    if sr is None:
        raise ValueError(f"帳冊紀錄不存在：id={session_record_id}")
    if sr.payment_status == "claimed":
        raise ValueError("已入帳的紀錄不能退回補件，請改用作廢核銷案")

    before = {
        "therapist_doc_submitted_at": sr.therapist_doc_submitted_at,
        "admin_verified_at": sr.admin_verified_at,
    }
    sr.therapist_doc_submitted_at = None
    sr.therapist_doc_submitted_by = None
    sr.admin_verified_at = None
    sr.admin_verified_by = None

    _notify_therapist_doc_returned(db, sr, reason)
    write_audit(db, "session_records", sr.id, "RETURN_FOR_CORRECTION", actor_id,
                before, {"therapist_doc_submitted_at": None, "admin_verified_at": None},
                reason=reason)
    db.flush()
    return sr


def _notify_therapist_doc_returned(db: Session, sr: SessionRecord, reason: str) -> None:
    """通知心理師。notifications 這張表在系統裡一直只被讀、沒被寫過
    （提醒都是讀取時即時算的），退回補件是第一個真的需要落地通知的情境
    ——心理師不會沒事去翻每一筆舊紀錄，系統得主動告訴他。"""
    if not sr.therapist_id:
        return
    db.add(Notification(
        user_id=sr.therapist_id,
        type="doc_pending",
        title="核銷文件被退回補件",
        message=f"{sr.session_date} 的場次文件需要補件：{reason}",
        link="/docs",
    ))
