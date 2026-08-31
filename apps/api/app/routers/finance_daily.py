"""Phase 4：日報表對帳、應收帳冊、月報表。

三者的關係：
    session_records ──(完成當日對帳)──> daily_closings ──(聚合)──> 月報表
                    └─(未收/月結/機構)─> 應收帳冊三分頁

月報表的資料來源**只有一個**：status='closed' 的 daily_closings。
未對帳的日在彙總表標「待對帳」，金額不計入合計、也不進心理師收入。
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.finance import DailyClosing, MonthlyReport, SupervisorReview
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services import receipt_number
from app.services.audit import write_audit

router = APIRouter(prefix="/finance", tags=["finance-daily"])

FINANCE_ROLES = ["admin", "accountant", "staff"]
SUPERVISOR_ROLES = ["admin", "accountant"]


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 日報表 / 對帳
# ---------------------------------------------------------------------------
class DailyRow(BaseModel):
    id: int
    session_date: date
    case_name: str | None
    therapist_name: str | None
    session_type: str
    amount: float
    self_pay_amount: float
    institution_claim_amount: float
    payment_status: str
    payment_track: str
    payment_method: str | None
    receipt_no: str | None
    is_no_show: bool
    no_show_fee: float


class DailySummary(BaseModel):
    closing_date: date
    status: str
    locked: bool
    cash_total: float
    transfer_total: float
    unpaid_total: float
    receivable_total: float
    record_count: int
    rows: list[DailyRow]


def _row(r: SessionRecord, db: Session) -> DailyRow:
    case = db.query(Case).filter(Case.id == r.case_id).first() if r.case_id else None
    th = db.query(User).filter(User.id == r.therapist_id).first()
    return DailyRow(
        id=r.id, session_date=r.session_date,
        case_name=case.name if case else None,
        therapist_name=th.name if th else None,
        session_type=r.session_type,
        amount=float(r.amount or 0),
        self_pay_amount=float(r.self_pay_amount or 0),
        institution_claim_amount=float(r.institution_claim_amount or 0),
        payment_status=r.payment_status,
        payment_track=r.payment_track,
        payment_method=r.payment_method,
        receipt_no=r.invoice.invoice_number if getattr(r, "invoice", None) else r.receipt_no,
        is_no_show=bool(r.is_no_show),
        no_show_fee=float(r.no_show_fee or 0),
    )


@router.get("/daily", response_model=DailySummary)
def daily_report(
    day: date = Query(...),
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    closing = db.query(DailyClosing).filter(DailyClosing.closing_date == day).first()
    records = db.query(SessionRecord).filter(SessionRecord.session_date == day).all()

    cash = sum(float(r.self_pay_amount or 0) for r in records
               if r.payment_status == "paid" and r.payment_method == "cash")
    transfer = sum(float(r.self_pay_amount or 0) for r in records
                   if r.payment_status == "paid" and r.payment_method == "transfer")
    # 當日應收未收：只計本來就該當場收卻沒收到的；月結與機構全額不算
    # （心智圖 §四.4）
    unpaid = sum(float(r.self_pay_amount or 0) for r in records
                 if r.payment_status == "unpaid" and r.payment_track == "immediate")
    receivable = sum(float(r.self_pay_amount or 0) for r in records)

    return DailySummary(
        closing_date=day,
        status=closing.status if closing else "pending",
        locked=bool(closing and closing.status == "closed"),
        cash_total=cash, transfer_total=transfer, unpaid_total=unpaid,
        receivable_total=receivable,
        record_count=len(records),
        rows=[_row(r, db) for r in records],
    )


class CloseBody(BaseModel):
    note: str | None = None


@router.post("/daily/{day}/close", response_model=DailySummary)
def close_day(
    day: date,
    body: CloseBody,
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    """完成當日對帳 → 鎖定。未收者隔日自動轉入應收帳冊追蹤。"""
    existing = db.query(DailyClosing).filter(DailyClosing.closing_date == day).first()
    if existing and existing.status == "closed":
        raise HTTPException(status_code=400, detail=f"{day} 已完成對帳並鎖定，需解鎖才能修改")

    summary = daily_report(day=day, user=user, db=db)
    closing = existing or DailyClosing(closing_date=day)
    closing.status = "closed"
    closing.cash_total = summary.cash_total
    closing.transfer_total = summary.transfer_total
    closing.unpaid_total = summary.unpaid_total
    closing.note = body.note
    closing.closed_at = _now()
    closing.closed_by = user.id
    db.add(closing)
    db.flush()

    db.query(SessionRecord).filter(SessionRecord.session_date == day).update(
        {SessionRecord.daily_closing_id: closing.id}, synchronize_session=False
    )
    write_audit(db, "daily_closings", closing.id, "UPDATE", user.id,
                {"status": "pending"}, {"status": "closed"})
    db.commit()
    return daily_report(day=day, user=user, db=db)


class UnlockBody(BaseModel):
    reason: str
    session_record_id: int | None = None


@router.post("/daily/{day}/unlock", status_code=http.HTTP_201_CREATED)
def unlock_day(
    day: date,
    body: UnlockBody,
    user: User = Depends(RequireRole(SUPERVISOR_ROLES)),
    db: Session = Depends(get_db),
):
    """解鎖已對帳的日期。此舉會寫入主管覆核紀錄。

    註：補收款**不**走這裡 —— 它自動回寫、不視為修改、不需解鎖、不列覆核。
    """
    closing = db.query(DailyClosing).filter(DailyClosing.closing_date == day).first()
    if not closing or closing.status != "closed":
        raise HTTPException(status_code=400, detail=f"{day} 尚未完成對帳，不需解鎖")
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="解鎖需填寫原因")

    closing.status = "pending"
    review = SupervisorReview(
        daily_closing_id=closing.id,
        session_record_id=body.session_record_id,
        unlock_reason=body.reason.strip(),
        unlocked_by=user.id,
    )
    db.add(review)
    write_audit(db, "daily_closings", closing.id, "UPDATE", user.id,
                {"status": "closed"}, {"status": "pending", "reason": body.reason})
    db.commit()
    return {"unlocked": True, "review_id": review.id}


# ---------------------------------------------------------------------------
# 應收帳冊：三個分頁分的是「追款方式」不是付款狀態
# ---------------------------------------------------------------------------
class ArRow(DailyRow):
    overdue_days: int
    severity: str  # none / warn（1-7天）/ urgent（>7天）


@router.get("/ar", response_model=list[ArRow])
def accounts_receivable(
    track: str = Query("immediate", pattern="^(immediate|monthly|institution)$"),
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(SessionRecord).filter(
        SessionRecord.payment_track == track,
        SessionRecord.payment_status.in_(["unpaid", "claiming"]),
        SessionRecord.is_void.is_(False),
    )
    if start:
        q = q.filter(SessionRecord.session_date >= start)
    if end:
        q = q.filter(SessionRecord.session_date <= end)

    today = date.today()
    out: list[ArRow] = []
    for r in q.order_by(SessionRecord.session_date).all():
        days = (today - r.session_date).days
        # 逾期天數分色（原型 ar）：黃 1-7 天、紅 超過 7 天
        sev = "none" if days <= 0 else ("warn" if days <= 7 else "urgent")
        out.append(ArRow(**_row(r, db).model_dump(), overdue_days=max(days, 0), severity=sev))
    return out


class PayBody(BaseModel):
    payment_method: str
    payment_note: str | None = None
    discount_amount: float = 0
    discount_note: str | None = None
    issue_receipt: bool = True


@router.post("/ar/{record_id}/pay", response_model=DailyRow)
def collect_payment(
    record_id: int,
    body: PayBody,
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    """就地收款。若該日已完成對帳，視為**補收款**：自動回寫、不需解鎖。"""
    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r.payment_status == "paid":
        raise HTTPException(status_code=400, detail="此筆已收款")
    if body.payment_method not in ("cash", "transfer"):
        raise HTTPException(status_code=400, detail="payment_method 需為 cash 或 transfer")

    r.payment_status = "paid"
    r.payment_method = body.payment_method
    r.payment_note = body.payment_note
    r.paid_at = _now()
    if body.discount_amount:
        r.discount_amount = body.discount_amount
        r.discount_note = body.discount_note

    closing = (
        db.query(DailyClosing).filter(DailyClosing.closing_date == r.session_date).first()
    )
    if closing and closing.status == "closed":
        # 補收款：回寫月報表該日，該列標小字「MM/DD 補收 $X」
        r.supplementary_paid_at = _now()

    if body.issue_receipt and r.invoice_id is None:
        inv = receipt_number.issue(db, r.session_date, session_record_id=r.id, created_by=user.id)
        r.invoice_id = inv.id

    write_audit(db, "session_records", r.id, "UPDATE", user.id,
                {"payment_status": "unpaid"},
                {"payment_status": "paid", "method": body.payment_method,
                 "supplementary": bool(r.supplementary_paid_at)})
    db.commit()
    db.refresh(r)
    return _row(r, db)


# ---------------------------------------------------------------------------
# 月報表：只收已完成對帳的每日紀錄
# ---------------------------------------------------------------------------
class MonthlyDay(BaseModel):
    day: date
    closed: bool
    cash_total: float
    transfer_total: float
    unpaid_total: float
    record_count: int


class TherapistIncome(BaseModel):
    therapist_id: int
    therapist_name: str | None
    counseling_income: float
    lecture_fee: float
    supervision_income: float
    venue_deduction: float
    total: float


class MonthlySummary(BaseModel):
    month: str
    status: str
    closed_days: int
    total_days: int
    cash_total: float
    transfer_total: float
    unpaid_total: float
    payout_date: date | None
    days: list[MonthlyDay]
    therapist_income: list[TherapistIncome]
    pending_reviews: int


@router.get("/monthly", response_model=MonthlySummary)
def monthly_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)

    closings = {
        c.closing_date: c
        for c in db.query(DailyClosing)
        .filter(DailyClosing.closing_date.between(first, last))
        .all()
    }
    counts = dict(
        db.query(SessionRecord.session_date, func.count(SessionRecord.id))
        .filter(SessionRecord.session_date.between(first, last))
        .group_by(SessionRecord.session_date)
        .all()
    )

    days: list[MonthlyDay] = []
    d = first
    while d <= last:
        c = closings.get(d)
        closed = bool(c and c.status == "closed")
        days.append(
            MonthlyDay(
                day=d, closed=closed,
                cash_total=float(c.cash_total) if closed else 0.0,
                transfer_total=float(c.transfer_total) if closed else 0.0,
                unpaid_total=float(c.unpaid_total) if closed else 0.0,
                record_count=counts.get(d, 0),
            )
        )
        d += timedelta(days=1)

    closed_days = [x for x in days if x.closed]
    # 只有「有紀錄的日」才需要對帳，全空的日不計入分母
    days_needing = [x for x in days if x.record_count > 0 or x.closed]

    # 心理師收入：只算已對帳日的紀錄
    closed_ids = [c.id for c in closings.values() if c.status == "closed"]
    income: list[TherapistIncome] = []
    if closed_ids:
        rows = (
            db.query(
                SessionRecord.therapist_id,
                func.coalesce(func.sum(SessionRecord.amount * func.coalesce(SessionRecord.commission_rate_used, 0)), 0),
            )
            .filter(
                SessionRecord.daily_closing_id.in_(closed_ids),
                SessionRecord.is_void.is_(False),
            )
            .group_by(SessionRecord.therapist_id)
            .all()
        )
        names = {u.id: u.name for u in db.query(User).all()}
        for tid, counseling in rows:
            income.append(
                TherapistIncome(
                    therapist_id=tid, therapist_name=names.get(tid),
                    counseling_income=float(counseling or 0),
                    # 講師費／督導收入／場地費扣項待 Q16/Q17 定案，先固定 0
                    # TODO(open_questions#Q16,#Q17)
                    lecture_fee=0.0, supervision_income=0.0, venue_deduction=0.0,
                    total=float(counseling or 0),
                )
            )

    report = db.query(MonthlyReport).filter(MonthlyReport.month == month).first()
    # 薪資發放日 = 結算月的隔月 25 日
    payout = date(y + (m == 12), (m % 12) + 1, 25)
    pending = (
        db.query(func.count(SupervisorReview.id))
        .join(DailyClosing)
        .filter(
            DailyClosing.closing_date.between(first, last),
            SupervisorReview.reviewed_at.is_(None),
        )
        .scalar()
        or 0
    )

    return MonthlySummary(
        month=month,
        status=report.status if report else "draft",
        closed_days=len(closed_days),
        total_days=len(days_needing),
        cash_total=sum(x.cash_total for x in closed_days),
        transfer_total=sum(x.transfer_total for x in closed_days),
        unpaid_total=sum(x.unpaid_total for x in closed_days),
        payout_date=report.payout_date if report and report.payout_date else payout,
        days=days,
        therapist_income=income,
        pending_reviews=pending,
    )


@router.get("/monthly/{month}/reviews")
def list_reviews(
    month: str,
    user: User = Depends(RequireRole(FINANCE_ROLES)),
    db: Session = Depends(get_db),
):
    """主管覆核紀錄：已對帳完成又解鎖修改的紀錄。"""
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    rows = (
        db.query(SupervisorReview, DailyClosing)
        .join(DailyClosing)
        .filter(DailyClosing.closing_date.between(first, last))
        .order_by(SupervisorReview.unlocked_at.desc())
        .all()
    )
    names = {u.id: u.name for u in db.query(User).all()}
    return [
        {
            "id": r.id,
            "day": c.closing_date,
            "reason": r.unlock_reason,
            "unlocked_by": names.get(r.unlocked_by),
            "unlocked_at": r.unlocked_at,
            "reviewed_by": names.get(r.reviewed_by),
            "reviewed_at": r.reviewed_at,
        }
        for r, c in rows
    ]
