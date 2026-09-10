from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.petty_cash import PettyCash
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    year, month = today.year, today.month

    base_q = db.query(SessionRecord).filter(
        extract("year", SessionRecord.session_date) == year,
        extract("month", SessionRecord.session_date) == month,
        SessionRecord.is_void.is_(False),
    )
    if user.role == "therapist":
        base_q = base_q.filter(SessionRecord.therapist_id == user.id)

    records = base_q.all()
    session_count = len(records)

    def _eff(r):
        return float(r.amount) - float(r.discount_amount or 0)

    total_revenue = sum(_eff(r) for r in records)
    unpaid_count = sum(1 for r in records if r.payment_status in ("unpaid", "claiming"))
    unpaid_amount = sum(_eff(r) for r in records if r.payment_status in ("unpaid", "claiming"))

    # Upcoming 7-day appointments needing reminders
    day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=7)
    range_str = f"[{day_start.isoformat()},{day_end.isoformat()})"

    reminder_q = db.query(func.count(Appointment.id)).filter(
        Appointment.status == "booked",
        text("time_range && :r").bindparams(r=range_str),
    )
    if user.role == "therapist":
        reminder_q = reminder_q.filter(Appointment.therapist_id == user.id)
    upcoming_count = reminder_q.scalar() or 0

    # Active case count
    case_q = db.query(func.count(Case.id)).filter(Case.status.in_(["initial", "ongoing"]))
    if user.role == "therapist":
        case_q = case_q.filter(Case.therapist_id == user.id)
    active_cases = case_q.scalar() or 0

    # Petty cash balance (admin/accountant only)
    petty_balance = None
    petty_alert = False
    if user.role in ("admin", "accountant"):
        last_petty = db.query(PettyCash).order_by(PettyCash.id.desc()).first()
        if last_petty:
            petty_balance = float(last_petty.balance_after)
            petty_alert = petty_balance < 3000

    # Churn warning count (cases with no future appointments, status ongoing)
    churn_count = 0
    if user.role in ("admin", "accountant"):
        now_str = f"[{day_start.isoformat()},)"
        active_case_ids = [c.id for c in db.query(Case.id).filter(Case.status.in_(["initial", "ongoing"])).all()]
        if active_case_ids:
            cases_with_future = set(
                r[0] for r in db.query(Appointment.case_id).filter(
                    Appointment.case_id.in_(active_case_ids),
                    Appointment.status == "booked",
                    text("time_range && :r").bindparams(r=now_str),
                ).distinct().all()
            )
            churn_count = len(set(active_case_ids) - cases_with_future)

    return {
        "session_count": session_count,
        "total_revenue": total_revenue,
        "unpaid_count": unpaid_count,
        "unpaid_amount": unpaid_amount,
        "upcoming_reminders": upcoming_count,
        "active_cases": active_cases,
        "petty_balance": petty_balance,
        "petty_alert": petty_alert,
        "churn_count": churn_count,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 今日待辦 — V2升級計畫 11 §4.1
#
# 為什麼需要這支：既有 GET /dashboard 只回傳彙總數字（本月場次、營收、未收
# 筆數）。那些都正確，但**沒有一個能讓人採取行動**——早上八點打開系統的人
# 要問的是「我今天要處理什麼」，不是「資料庫裡有幾筆」。
#
# v7 營運總覽定案的三條規則決定了這支的形狀：
#   ① 依**急迫度**排序（逾期媒合 → 今日初診 → 額度將盡 → 核銷缺件 → 逾期收款）
#   ② 每列**就地執行**，所以每筆都要帶 href 與 action 文字
#   ③ 做完該列即時消失 —— 所以這裡一律**即時查詢**，不落地成待辦表；
#      狀態一改，下次查就自然不見了，不會有「已讀但其實沒處理」的假象
#
# 尚未做：v7 待確認 ② 的「延後處理」。依 11 §4.1 應該做成 snoozed_until
# （而不是「已讀」），但那需要一張新表與 migration，等這頁實際用起來、確認
# 哪幾類待辦真的會重複出現再補。
# ═══════════════════════════════════════════════════════════════════════════

# 派案逾期天數。v7 定案 ④：逾 1 天提醒、逾 3 個自然日自動退回。
REFERRAL_OVERDUE_DAYS = 1
# 應收逾期天數。當日未收只是還沒收，超過這個天數才是真的漏了。
UNPAID_OVERDUE_DAYS = 7
# 每一類待辦最多列幾筆，其餘收成「還有 N 筆」（見 _cap_per_kind）。
MAX_PER_KIND = 5
# 額度將盡只在「近期還有預約」時才算待辦。
QUOTA_LOOKAHEAD_DAYS = 14


def _todo(kind, label, tone, title, subject, href, action, urgency, **extra):
    return {
        "id": f"{kind}:{extra.pop('ref_id')}",
        "kind": kind,
        "label": label,
        "tone": tone,
        "title": title,
        "subject": subject,
        "href": href,
        "action": action,
        "urgency": urgency,
        **extra,
    }


@router.get("/todos")
def dashboard_todos(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """營運總覽的待辦佇列。依急迫度排序，每筆都可就地跳到能處理它的地方。"""
    from app.institution.models.enrollment import InstEnrollment
    from app.models.claim_batch import ClaimBatch
    from app.models.institution import Institution  # noqa: F401  (relationship 需要)
    from app.referral.models.batch import ReferralBatch, ReferralBatchMember
    from app.referral.models.referral import Referral

    today = date.today()
    todos: list[dict] = []

    # 心理師不進本頁（v7：改看心理師版「我的今日」）。
    if user.role == "therapist":
        return {"todos": [], "as_of": today.isoformat()}

    is_ops = user.role in ("admin", "staff")

    # ── ① 逾期媒合：派出去超過 N 天還沒有人回覆 ──────────────────────────
    if is_ops:
        cutoff = datetime.now(timezone.utc) - timedelta(days=REFERRAL_OVERDUE_DAYS)
        rows = (
            db.query(Referral, ReferralBatch.sent_at)
            .join(ReferralBatch, ReferralBatch.referral_id == Referral.id)
            .join(ReferralBatchMember, ReferralBatchMember.batch_id == ReferralBatch.id)
            .filter(
                ReferralBatch.is_open.is_(True),
                ReferralBatchMember.reply_status == "pending",
                ReferralBatch.sent_at < cutoff,
                Referral.status.notin_(["closed", "cancelled", "converted"]),
            )
            .distinct()
            .all()
        )
        for ref, sent_at in rows:
            days = (datetime.now(timezone.utc) - sent_at).days if sent_at else 0
            todos.append(
                _todo(
                    "referral", "媒合", "danger",
                    f"待心理師回覆逾 {days} 天",
                    f"{ref.name}（{ref.referral_code}）",
                    f"/match?referral={ref.id}", "改派",
                    # 拖愈久愈上面，但整類都排在最前面
                    1000 + min(days, 30),
                    ref_id=ref.id,
                )
            )

    # ── ② 今日初診待確認到診 ────────────────────────────────────────────
    # 「初診」＝個案還在流水號階段（status='initial'，尚未產生病歷號）。
    if is_ops:
        day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        day_range = f"[{day_start.isoformat()},{(day_start + timedelta(days=1)).isoformat()})"
        rows = (
            db.query(Appointment, Case)
            .join(Case, Case.id == Appointment.case_id)
            .filter(
                Appointment.status == "booked",
                Appointment.check_in_status == "pending",
                Case.status == "initial",
                text("time_range && :r").bindparams(r=day_range),
            )
            .all()
        )
        for appt, case in rows:
            when = appt.time_range.lower.astimezone().strftime("%H:%M") if appt.time_range else ""
            todos.append(
                _todo(
                    "first_visit", "初診", "active",
                    "今日初診待確認到診",
                    f"{case.name} {when}".strip(),
                    "/rooms", "報到",
                    900,
                    ref_id=appt.id,
                )
            )

    # ── ③ 額度將盡 ──────────────────────────────────────────────────────
    # 只有「額度快沒了」還不構成待辦——半年前用完的方案永遠掛在那裡不會有人處理。
    # 真正要行政動作的是：**這個人接下來還要來，而且來的時候金額會變**
    # （機構額度用罄 → 自動回落自費）。所以條件是額度將盡 ＋ 近期還有待報到的預約。
    if is_ops:
        soon = datetime.now(timezone.utc)
        soon_range = f"[{soon.isoformat()},{(soon + timedelta(days=QUOTA_LOOKAHEAD_DAYS)).isoformat()})"
        rows = (
            db.query(InstEnrollment)
            .filter(
                InstEnrollment.status == "active",
                InstEnrollment.quota_unit == "count",
                InstEnrollment.reserved_count <= 1,
            )
            .all()
        )
        for e in rows:
            upcoming = (
                db.query(func.count(Appointment.id))
                .filter(
                    Appointment.case_id == e.case_id,
                    Appointment.status == "booked",
                    Appointment.check_in_status == "pending",
                    text("time_range && :r").bindparams(r=soon_range),
                )
                .scalar()
                or 0
            )
            if not upcoming:
                continue
            remaining = int(float(e.reserved_count or 0))
            case_name = e.case.name if e.case else f"#{e.case_id}"
            plan_name = e.plan.name if e.plan else f"方案 {e.plan_id}"
            todos.append(
                _todo(
                    "quota", "額度", "warn",
                    ("額度已用罄，下次起自動轉自費" if remaining == 0
                     else "機構額度剩最後 1 次"),
                    f"{case_name} · {plan_name}",
                    f"/cases?case={e.case_id}", "設定下次結帳",
                    800 + (5 if remaining == 0 else 0),
                    ref_id=e.id,
                )
            )

    # ── ④ 核銷缺件：已收納進核銷批次，但心理師文件還沒交 ────────────────
    # 只看**還沒結束**的批次。已入帳（received）的批次即使有欄位沒填，也不是
    # 今天要處理的事——實測資料庫裡 49 個有缺件的批次有 45 個已經 received，
    # 全列出來等於用雜訊把真正要處理的 4 個蓋掉。
    if is_ops or user.role == "accountant":
        rows = (
            db.query(SessionRecord)
            .join(ClaimBatch, ClaimBatch.id == SessionRecord.claim_batch_id)
            .filter(
                SessionRecord.is_void.is_(False),
                SessionRecord.therapist_doc_submitted_at.is_(None),
                ClaimBatch.status.notin_(["received", "closed", "void"]),
            )
            .all()
        )
        by_batch: dict[int, int] = {}
        for r in rows:
            by_batch[r.claim_batch_id] = by_batch.get(r.claim_batch_id, 0) + 1
        for batch_id, n in by_batch.items():
            todos.append(
                _todo(
                    "claim_doc", "核銷", "warn",
                    f"心理師文件未齊（{n} 筆）",
                    f"核銷批次 #{batch_id}",
                    f"/claims?batch={batch_id}", "前往核對",
                    700,
                    ref_id=batch_id,
                    count=n,
                )
            )

    # ── ⑤ 逾期收款 ──────────────────────────────────────────────────────
    # 依 09 §1.4a：**不分 funding_source**。機構案的個案自付額走 copay_collected_at，
    # 純自費案走 payment_status——既有 /ledger 的未收查詢只認 self_pay，所以機構案
    # 的自付額從來不會被算成「未收」。這裡用統一條件，不複製那個 bug。
    overdue_before = today - timedelta(days=UNPAID_OVERDUE_DAYS)
    rows = (
        db.query(SessionRecord, Case)
        .outerjoin(Case, Case.id == SessionRecord.case_id)
        .filter(
            SessionRecord.is_void.is_(False),
            SessionRecord.session_date < overdue_before,
            SessionRecord.copay_collected_at.is_(None),
            SessionRecord.payment_status == "unpaid",
        )
        .order_by(SessionRecord.session_date)
        .limit(50)
        .all()
    )
    unpaid: list[tuple] = []
    for rec, case in rows:
        payable = float(rec.case_payable if rec.case_payable is not None else rec.amount)
        payable -= float(rec.discount_amount or 0)
        if payable <= 0:
            continue
        unpaid.append((rec, case, payable, (today - rec.session_date).days))

    for rec, case, payable, days in unpaid:
        todos.append(
            _todo(
                "unpaid", "收款", "danger",
                f"逾期 {days} 天未收",
                f"{case.name if case else '—'} ${payable:,.0f}",
                "/ar", "收款",
                600 + min(days, 60),
                ref_id=rec.id,
                amount=payable,
            )
        )

    todos.sort(key=lambda t: -t["urgency"])
    return {"todos": _cap_per_kind(todos), "as_of": today.isoformat()}


def _cap_per_kind(todos: list[dict]) -> list[dict]:
    """每一類最多列 MAX_PER_KIND 筆，其餘收成一列「還有 N 筆」。

    待辦清單的每一列都應該是**一個動作**。長尾會把「今天真的要做的事」擠出
    畫面——實測一年份資料會產生 48 筆逾期未收與 14 筆額度用罄，全部攤開就跟
    改寫前那四張 SELECT COUNT 一樣沒有用。追討 48 筆的動作是「打開應收帳冊」，
    不是 48 件事。
    """
    OVERFLOW = {
        "unpaid": ("收款", "danger", "/ar", "前往追收"),
        "quota": ("額度", "warn", "/cases?filter=quota_exhausted", "查看全部"),
        "claim_doc": ("核銷", "warn", "/claims", "前往核對"),
        "referral": ("媒合", "danger", "/match", "查看全部"),
        "first_visit": ("初診", "active", "/rooms", "前往報到"),
    }
    out: list[dict] = []
    seen: dict[str, int] = {}
    overflow: dict[str, list[dict]] = {}

    for t in todos:
        k = t["kind"]
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= MAX_PER_KIND:
            out.append(t)
        else:
            overflow.setdefault(k, []).append(t)

    for kind, rest in overflow.items():
        label, tone, href, action = OVERFLOW.get(kind, ("其他", "pending", "/dashboard", "查看"))
        total = sum(float(t.get("amount") or 0) for t in rest)
        out.append(
            {
                "id": f"{kind}:more",
                "kind": kind,
                "label": label,
                "tone": tone,
                "title": f"還有 {len(rest)} 筆{'同類待辦' if not total else ''}",
                "subject": f"合計 ${total:,.0f}" if total else "",
                "href": href,
                "action": action,
                # 永遠排在該類最後一筆之後
                "urgency": min(t["urgency"] for t in rest) - 1,
                "count": len(rest),
            }
        )

    out.sort(key=lambda t: -t["urgency"])
    return out
