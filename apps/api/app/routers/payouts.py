from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.session_record import SessionRecord
from app.models.venue_rental import VenueRental
from app.models.therapist_payout import PayoutDetail, TherapistPayout
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/payouts", tags=["payouts"])

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def _get_rate(sr: SessionRecord) -> Decimal:
    if sr.commission_rate_used is not None:
        return Decimal(str(sr.commission_rate_used))
    return DEFAULT_COMMISSION_RATE


def payout_line_amount(sr: SessionRecord) -> Decimal:
    """單筆場次對心理師酬勞的貢獻。三種薪酬模式走三條路（07 §8.2）。

    commission（抽成，絕大多數）
        有效金額 × 抽成率 ＋ 外出保底。有效金額優先用 commissionable_base
        ——那是報價當下就算好的「可抽成基數」，會排除不該抽成的部分（例如
        交通費）；沒有快照時退回 amount − 優待減免。

    kickback（回扣制，如教支中心）
        鐘點費由心理師自己向機構請領，診所抽的那份要**由心理師回繳**。
        所以這筆對「診所要發給心理師的錢」是**負的**：−(有效金額 × (1−抽成率))。
        原本的程式碼把它跟抽成制走同一條公式，等於診所倒過來付錢給心理師，
        金額還是最大的那種錯——回扣制的方案愈多、月結算就錯愈多。

    none（無心理師勞務，如借場地）
        不計酬，回 0。

    作廢紀錄一律 0：原本沒有濾掉 is_void，作廢的場次照樣計酬。
    """
    if sr.is_void:
        return Decimal("0")

    mode = sr.compensation_mode or "commission"
    if mode == "none":
        return Decimal("0")

    if sr.commissionable_base is not None:
        base = Decimal(str(sr.commissionable_base))
    else:
        base = Decimal(str(sr.amount)) - Decimal(str(sr.discount_amount or 0))

    rate = _get_rate(sr)
    if mode == "kickback":
        return (-(base * (Decimal("1") - rate))).quantize(Decimal("0.01"))
    return (base * rate + Decimal(str(sr.outcall_bonus or 0))).quantize(Decimal("0.01"))


class PayoutResponse(BaseModel):
    id: int
    therapist_id: int
    therapist_name: str | None = None
    payout_month: str
    total_amount: float
    session_count: int = 0
    status: str
    paid_at: str | None = None


def venue_deductions(db: Session, therapist_id: int, year: int, month: int) -> list[VenueRental]:
    """該心理師當月要從酬勞扣回的場地費 —— 07 §8.2 / 06 P6 的督導模式 A/B。

        模式 A  櫃台代收督導費、開立收據，**場地費自動 $0**（診所收的是督導費）
                → 沒有東西要扣
        模式 B  心理師自收督導費，**場地費照收並由酬勞回扣**
                → 這筆要從當月酬勞扣下來

    判準是 `payer`，不是 `supervision_fee_mode`：未到時付款方會改成「借用人
    自付」（場地已經被佔住了，成本不會因為人沒來就消失），那種就不從酬勞扣。

    10 §7.1 把這件事標成「部分完成：計算與場地租借的連結已建，酬勞單上的
    扣回明細列尚未呈現」——實際查證後更嚴重：`generate_payouts` 完全沒有
    引用 VenueRental，所以**不是明細沒顯示，是錢根本沒扣**。
    """
    return (
        db.query(VenueRental)
        .filter(
            VenueRental.renter_therapist_id == therapist_id,
            VenueRental.renter_kind == "private",
            VenueRental.payer == "therapist",
            VenueRental.status != "cancelled",
            extract("year", func.lower(VenueRental.time_range)) == year,
            extract("month", func.lower(VenueRental.time_range)) == month,
        )
        .all()
    )


def venue_deduction_total(db: Session, therapist_id: int, year: int, month: int) -> Decimal:
    return sum(
        (Decimal(str(v.amount or 0)) for v in venue_deductions(db, therapist_id, year, month)),
        Decimal("0"),
    )


@router.get("", response_model=list[PayoutResponse])
def list_payouts(
    payout_month: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TherapistPayout)
    if user.role == "therapist":
        q = q.filter(TherapistPayout.therapist_id == user.id)
    if payout_month:
        q = q.filter(TherapistPayout.payout_month == payout_month)
    payouts = q.order_by(TherapistPayout.payout_month.desc(), TherapistPayout.id).all()

    therapist_ids = list({p.therapist_id for p in payouts})
    names = {}
    if therapist_ids:
        users = db.query(User).filter(User.id.in_(therapist_ids)).all()
        names = {u.id: u.name for u in users}

    result = []
    for p in payouts:
        detail_count = db.query(PayoutDetail).filter(PayoutDetail.payout_id == p.id).count()
        result.append(PayoutResponse(
            id=p.id,
            therapist_id=p.therapist_id,
            therapist_name=names.get(p.therapist_id),
            payout_month=p.payout_month,
            total_amount=float(p.total_amount),
            session_count=detail_count,
            status=p.status,
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
        ))
    return result


@router.get("/{payout_id}/details")
def payout_details(
    payout_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payout = db.query(TherapistPayout).filter(TherapistPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if user.role == "therapist" and payout.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    details = db.query(PayoutDetail).filter(PayoutDetail.payout_id == payout_id).all()
    sessions = []
    for d in details:
        sr = db.query(SessionRecord).filter(SessionRecord.id == d.session_id).first()
        if sr:
            rate = _get_rate(sr)
            bonus = float(sr.outcall_bonus or 0)
            sessions.append({
                "session_id": sr.id,
                "session_date": sr.session_date.isoformat(),
                "amount": float(sr.amount),
                # 明細與總額共用 payout_line_amount()，避免兩邊各算各的而對不起來
                "therapist_share": float(payout_line_amount(sr)),
                "compensation_mode": sr.compensation_mode or "commission",
                "outcall_bonus": bonus,
                "fee_category": sr.fee_category,
                "session_type": sr.session_type,
            })
    # 依 09 §4.3，酬勞單分三區呈現。前端不重新分類——這裡就分好。
    y, m = (int(x) for x in payout.payout_month.split("-"))
    rentals = venue_deductions(db, payout.therapist_id, y, m)
    deductions = [
        {
            "rental_id": v.id,
            "rental_no": v.rental_no,
            "date": v.time_range.lower.date().isoformat() if v.time_range else None,
            "purpose": v.purpose,
            "supervision_fee_mode": v.supervision_fee_mode,
            "amount": float(v.amount or 0),
        }
        for v in rentals
    ]

    commission = [s for s in sessions if s["compensation_mode"] == "commission"]
    kickback = [s for s in sessions if s["compensation_mode"] == "kickback"]
    other = [s for s in sessions if s["compensation_mode"] not in ("commission", "kickback")]

    return {
        "payout_id": payout_id,
        "payout_month": payout.payout_month,
        "status": payout.status,
        "total_amount": float(payout.total_amount or 0),
        # 保留原欄位給既有呼叫端；下面三區是 09 §4.3 要求的分區呈現
        "sessions": sessions,
        "commission_sessions": commission,
        "kickback_sessions": kickback,
        "other_sessions": other,
        "venue_deductions": deductions,
        "subtotals": {
            "commission": round(sum(s["therapist_share"] for s in commission), 2),
            # 回饋制是**扣項**：心理師先向機構收到全額，診所抽的那份要回繳。
            # 混在同一張表會讓心理師誤讀成收入（09 §1.6）。
            "kickback": round(sum(s["therapist_share"] for s in kickback), 2),
            "other": round(sum(s["therapist_share"] for s in other), 2),
            "venue": round(sum(d["amount"] for d in deductions), 2),
        },
    }


class GeneratePayoutRequest(BaseModel):
    payout_month: str  # YYYY-MM


@router.post("/generate")
def generate_payouts(
    body: GeneratePayoutRequest,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    parts = body.payout_month.split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    year, month = int(parts[0]), int(parts[1])

    records = (
        db.query(SessionRecord)
        .filter(
            extract("year", SessionRecord.session_date) == year,
            extract("month", SessionRecord.session_date) == month,
            SessionRecord.is_void.is_(False),  # 作廢的場次不計酬
        )
        .all()
    )

    by_therapist: dict[int, list[SessionRecord]] = {}
    for r in records:
        by_therapist.setdefault(r.therapist_id, []).append(r)

    created = updated = 0
    # 每位心理師都要算，即使當月沒有場次——只有場地費要扣的情況也得產生酬勞單
    all_tids = set(by_therapist) | {
        v.renter_therapist_id
        for v in db.query(VenueRental)
        .filter(
            VenueRental.renter_kind == "private",
            VenueRental.payer == "therapist",
            VenueRental.status != "cancelled",
            extract("year", func.lower(VenueRental.time_range)) == year,
            extract("month", func.lower(VenueRental.time_range)) == month,
        )
        .all()
        if v.renter_therapist_id
    }
    for tid in all_tids:
        recs = by_therapist.get(tid, [])
        # 場次酬勞 −（該心理師當月自付的場地費）。原本完全沒扣這一段，
        # 等於心理師被多發了他們該付的場地費（見 venue_deductions）。
        total = float(
            sum(payout_line_amount(r) for r in recs)
            - venue_deduction_total(db, tid, year, month)
        )

        existing = db.query(TherapistPayout).filter(
            TherapistPayout.therapist_id == tid,
            TherapistPayout.payout_month == body.payout_month,
        ).first()

        if existing:
            # Only update pending payouts; skip already-paid ones
            if existing.status == "paid":
                continue
            existing.total_amount = total
            db.query(PayoutDetail).filter(PayoutDetail.payout_id == existing.id).delete()
            db.flush()
            for r in recs:
                db.add(PayoutDetail(payout_id=existing.id, session_id=r.id))
            updated += 1
        else:
            payout = TherapistPayout(
                therapist_id=tid,
                payout_month=body.payout_month,
                total_amount=total,
                status="pending",
                created_by=user.id,
            )
            db.add(payout)
            db.flush()
            for r in recs:
                db.add(PayoutDetail(payout_id=payout.id, session_id=r.id))
            created += 1

    db.commit()
    return {"month": body.payout_month, "payouts_created": created, "payouts_updated": updated}


@router.put("/{payout_id}/pay")
def mark_paid(
    payout_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    payout = db.query(TherapistPayout).filter(TherapistPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status == "paid":
        raise HTTPException(status_code=400, detail="Already paid")
    payout.status = "paid"
    payout.paid_at = datetime.now(timezone.utc)
    write_audit(db, "therapist_payouts", payout.id, "UPDATE", user.id,
                {"status": "pending"}, {"status": "paid", "paid_at": payout.paid_at.isoformat()})
    db.commit()
    return {"status": "paid"}
