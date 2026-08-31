"""核銷、收款與回扣的規則。

來源：《系統架構規劃與機構合約清冊 對照確認事項 — 慈恩回覆》。
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.claim_batch import ClaimBatch
from app.models.institution_plan import InstitutionPlan
from app.models.session_record import SessionRecord
from app.models.user import User

INCOME_TAX_RATE = Decimal("0.10")  # 所得稅 10%

CLAIM_MODES = {
    "monthly": "月核銷（前一個月份的紀錄）",
    "quarterly": "季核銷（前三個月份的紀錄）",
    "semester": "學期核銷（上／下學期的紀錄）",
    "threshold": "次數達標（以達標那個月份送出）",
}

FUNDING_MODES = {
    "claim_first": "先核銷，後撥款",
    "prepay_then_claim": "先撥款，後核銷（類似儲值）",
    "prepay_no_claim": "先撥款，不核銷，後補收據",
}


# ---------------------------------------------------------------------------
# 撈紀錄的參考區間
#
# ⚠️ 這只是「建議撈哪些紀錄」，**不綁定**核銷案。
#    最終區間在送出核銷時才寫入 final_period_start/end。
# ---------------------------------------------------------------------------
def suggested_period(claim_mode: str, ref: date | None = None) -> tuple[date | None, date | None]:
    d = ref or date.today()
    if claim_mode == "monthly":
        end = date(d.year, d.month, 1) - timedelta(days=1)
        return date(end.year, end.month, 1), end
    if claim_mode == "quarterly":
        end = date(d.year, d.month, 1) - timedelta(days=1)
        start_month = end.month - 2
        start_year = end.year
        if start_month <= 0:
            start_month += 12
            start_year -= 1
        return date(start_year, start_month, 1), end
    if claim_mode == "semester":
        # 上學期 8/1–1/31、下學期 2/1–7/31
        if 2 <= d.month <= 7:
            return date(d.year, 2, 1), date(d.year, 7, 31)
        year = d.year if d.month >= 8 else d.year - 1
        return date(year, 8, 1), date(year + 1, 1, 31)
    # threshold：沒有固定區間，由達標判斷
    return None, None


# ---------------------------------------------------------------------------
# 送出前的漏單提醒
#
# 慈恩：「如果有漏掉紀錄，在送出核銷時會跳出提醒，以確認這幾筆沒有選到的
#        紀錄是『下個月才要核銷』，還是『真的是遺漏掉』」
# ---------------------------------------------------------------------------
def missing_records(db: Session, batch: ClaimBatch) -> list[dict]:
    """回傳「符合此核銷案的方案與區間、但未被納入任何核銷案」的紀錄。"""
    from app.models.claim_extra import ClaimBatchPlan

    plan_ids = [
        r.plan_id for r in
        db.query(ClaimBatchPlan).filter(ClaimBatchPlan.claim_batch_id == batch.id).all()
    ]
    if not plan_ids:
        return []

    q = (
        db.query(SessionRecord)
        .join(CaseInstitutionQuota, CaseInstitutionQuota.case_id == SessionRecord.case_id)
        .filter(
            CaseInstitutionQuota.plan_id.in_(plan_ids),
            SessionRecord.funding_source == "institution",
            SessionRecord.is_void.is_(False),
            SessionRecord.claim_batch_id.is_(None),
        )
    )
    if batch.period_start:
        q = q.filter(SessionRecord.session_date >= batch.period_start)
    if batch.period_end:
        q = q.filter(SessionRecord.session_date <= batch.period_end)

    names = {u.id: u.name for u in db.query(User).all()}
    return [
        {
            "id": r.id,
            "session_date": r.session_date,
            "case_name": r.case.name if getattr(r, "case", None) else None,
            "therapist_name": names.get(r.therapist_id),
            "institution_claim_amount": float(r.institution_claim_amount or 0),
        }
        for r in q.order_by(SessionRecord.session_date).all()
    ]


# ---------------------------------------------------------------------------
# Q27：核銷登記時數在「建立核銷案時」才轉出
# ---------------------------------------------------------------------------
def register_claim_hours(db: Session, record: SessionRecord, now) -> None:
    """把方案價目上的核銷登記時數與單價寫進帳冊紀錄。

    多數方案沒有設定，則沿用實際金額（登記時數 1、單價＝機構請款額）。
    """
    from app.models.institution_plan import PlanRateItem

    if record.claim_registered_at is not None:
        return  # 已登記過，不覆寫

    item = (
        db.query(PlanRateItem).filter(PlanRateItem.id == record.rate_item_id).first()
        if record.rate_item_id else None
    )
    if item and item.claim_hours is not None and item.claim_unit_rate is not None:
        record.claim_hours = item.claim_hours
        record.claim_unit_rate = item.claim_unit_rate
    else:
        record.claim_hours = Decimal("1")
        record.claim_unit_rate = Decimal(str(record.institution_claim_amount or 0))
    record.claim_registered_at = now


# ---------------------------------------------------------------------------
# Q28：回扣金額
#
# 慈恩：「依方案的鐘點費＋心理師個別的抽成，去計算回扣的金額」
#        「回繳方式：當月酬勞扣除」
#
# 機構把全額匯給心理師，心理師依抽成留下自己那份，其餘回繳慈恩：
#     回扣 = 機構請款額 × (1 − 心理師抽成率)
# 合約若填了 rebate_rate 則以該值覆寫。
# ---------------------------------------------------------------------------
def compute_rebate(contract, record: SessionRecord, commission_rate) -> Decimal | None:
    if contract is None or contract.settlement_direction != "to_therapist":
        return None
    base = Decimal(str(record.institution_claim_amount or 0))
    if contract.rebate_rate is not None:
        rate = Decimal(str(contract.rebate_rate))
    else:
        rate = Decimal("1") - Decimal(str(commission_rate or 0))
    return (base * rate).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# 收款試算（機構清冊畫面）
#
# 欄位：方案／申請金額／收款日期／收款金額／是否扣除所得稅 10%／
#       轉帳手續費／實際入帳金額
# ---------------------------------------------------------------------------
def settle_receipt(
    received_amount: Decimal | float,
    *,
    tax_withheld: bool,
    transfer_fee: Decimal | float = 0,
) -> dict:
    received = Decimal(str(received_amount))
    tax = (received * INCOME_TAX_RATE).quantize(Decimal("0.01")) if tax_withheld else Decimal("0")
    fee = Decimal(str(transfer_fee or 0))
    return {
        "received_amount": received,
        "tax_amount": tax,
        "transfer_fee": fee,
        "net_amount": received - tax - fee,
    }


def applied_total(db: Session, batch: ClaimBatch) -> Decimal:
    """此核銷案的申請金額＝納入紀錄的機構請款額合計。"""
    total = (
        db.query(func.coalesce(func.sum(SessionRecord.institution_claim_amount), 0))
        .filter(
            SessionRecord.claim_batch_id == batch.id,
            SessionRecord.is_void.is_(False),
        )
        .scalar()
    )
    return Decimal(str(total or 0))
