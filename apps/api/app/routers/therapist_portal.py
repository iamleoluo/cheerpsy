"""Phase 6：心理師端「我的今日」、「我的酬勞」、可當診時段。

可見範圍原則（原型 today／pay）：
  - 只看得到自己的資料
  - 不顯示收款金額與收據操作（屬櫃檯行政）
  - 不顯示他人個案、所內總營收、機構合約金額細節
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.appointment import Appointment
from app.models.availability import PERIODS, TherapistAvailability
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.finance import DailyClosing
from app.models.referral import ReferralDispatch, ReferralDispatchTarget
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/me", tags=["therapist-portal"])
THERAPIST = ["therapist"]


# ---------------------------------------------------------------------------
# 我的今日
# ---------------------------------------------------------------------------
@router.get("/today")
def my_today(
    day: date | None = Query(None),
    user: User = Depends(RequireRole(THERAPIST)),
    db: Session = Depends(get_db),
):
    d = day or date.today()
    start = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
    appts = (
        db.query(Appointment)
        .filter(
            Appointment.therapist_id == user.id,
            Appointment.time_range.op("&&")(
                func.tstzrange(start, start + timedelta(days=1))
            ),
        )
        .all()
    )
    schedule = []
    for a in sorted(appts, key=lambda x: x.time_range.lower):
        quota = None
        if a.quota_id:
            q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == a.quota_id).first()
            if q:
                quota = {
                    "used": q.used_count,
                    "total": q.total_count,
                    "is_last": (q.reserved_count + q.booked_count) == 1,
                }
        schedule.append({
            "id": a.id,
            "case_name": a.case.name if a.case else None,
            "start": a.time_range.lower,
            "end": a.time_range.upper,
            "session_type": a.session_type,
            "room_name": a.room.name if a.room else None,
            "status": a.status,
            "checkin_status": a.checkin_status,
            # 現場個案由櫃檯報到，心理師端不提供操作
            "action": "front_desk" if a.room_id else "self",
            "funding_source": a.funding_source,
            "quota": quota,
        })

    # 待辦依急迫度排序：派案邀請 → 文件確認 → 額度提醒
    pending_invites = (
        db.query(func.count(ReferralDispatchTarget.id))
        .filter(
            ReferralDispatchTarget.therapist_id == user.id,
            ReferralDispatchTarget.status == "pending",
        )
        .scalar() or 0
    )
    pending_docs = (
        db.query(func.count(SessionRecord.id))
        .filter(
            SessionRecord.therapist_id == user.id,
            SessionRecord.funding_source == "institution",
            SessionRecord.claim_batch_id.isnot(None),
            SessionRecord.therapist_doc_submitted_at.is_(None),
            SessionRecord.is_void.is_(False),
        )
        .scalar() or 0
    )
    last_session_cases = [
        s["case_name"] for s in schedule if s["quota"] and s["quota"]["is_last"]
    ]

    todos = []
    if pending_invites:
        todos.append({"type": "invite", "label": "派案邀請待回覆", "count": pending_invites, "link": "/pool"})
    if pending_docs:
        todos.append({"type": "doc", "label": "核銷文件待確認", "count": pending_docs, "link": "/docs"})
    for name in last_session_cases:
        todos.append({"type": "quota", "label": f"{name} 機構額度最後一次，下次轉自費", "count": 1, "link": "/sched"})

    return {
        "date": d,
        "schedule": schedule,
        "todos": todos,
        "stats": {
            "today_sessions": len([s for s in schedule if s["status"] != "cancelled"]),
            "pending_invites": pending_invites,
            "pending_docs": pending_docs,
        },
    }


# ---------------------------------------------------------------------------
# 我的酬勞
# ---------------------------------------------------------------------------
@router.get("/payout")
def my_payout(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    q: str | None = Query(None, description="搜尋個案姓名，方便確認紀錄"),
    user: User = Depends(RequireRole(THERAPIST)),
    db: Session = Depends(get_db),
):
    """資料來源＝月報表：只計已完成當日對帳的紀錄。

    抽成率在場次結算當下鎖定（commission_rate_used），日後調整抽成不影響
    已結算紀錄。鐘點費回溯修改**不自動重算**，會標記提示（Q22）。
    """
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)

    closed_ids = [
        c.id for c in db.query(DailyClosing).filter(
            DailyClosing.closing_date.between(first, last),
            DailyClosing.status == "closed",
        ).all()
    ]

    rows = db.query(SessionRecord).filter(
        SessionRecord.therapist_id == user.id,
        SessionRecord.session_date.between(first, last),
        SessionRecord.is_void.is_(False),
    ).order_by(SessionRecord.session_date).all()

    details = []
    settled_total = 0.0
    for r in rows:
        rate = float(r.commission_rate_used or 0)
        effective = float(r.amount or 0) - float(r.discount_amount or 0)
        share = round(effective * rate, 2) + float(r.outcall_bonus or 0)
        is_settled = r.daily_closing_id in closed_ids if r.daily_closing_id else False
        if is_settled:
            settled_total += share
        if q and q not in (r.case.name if getattr(r, "case", None) else ""):
            continue
        details.append({
            "id": r.id,
            "session_date": r.session_date,
            "case_name": r.case.name if getattr(r, "case", None) else None,
            "session_type": r.session_type,
            # 看得到場次金額（作為計算依據），看不到個案是否已付款與收據
            "amount": float(r.amount or 0),
            "discount_amount": float(r.discount_amount or 0),
            "commission_rate": rate,
            "outcall_bonus": float(r.outcall_bonus or 0),
            "share": share,
            "status": "settled" if is_settled else "pending",
        })

    return {
        "month": month,
        # 結算區間當月 1 日～月末，薪資發放日隔月 25 日
        "period_start": first,
        "period_end": last,
        "payout_date": date(y + (m == 12), (m % 12) + 1, 25),
        "settled_total": round(settled_total, 2),
        "pending_count": len([d for d in details if d["status"] == "pending"]),
        "details": details,
        "note": (
            "只計已完成當日對帳的紀錄；未對帳的日不計入。"
            "抽成率在場次結算當下鎖定，日後調整不影響已結算紀錄。"
        ),
    }


# ---------------------------------------------------------------------------
# 可當診時段
# ---------------------------------------------------------------------------
class AvailabilityBody(BaseModel):
    slots: list[dict]  # [{"weekday": 0-6, "period": "morning"}]


@router.get("/availability")
def get_availability(
    user: User = Depends(RequireRole(THERAPIST)),
    db: Session = Depends(get_db),
):
    rows = db.query(TherapistAvailability).filter(
        TherapistAvailability.therapist_id == user.id
    ).all()
    return {
        "periods": PERIODS,
        "slots": [{"weekday": r.weekday, "period": r.period} for r in rows],
    }


@router.put("/availability")
def set_availability(
    body: AvailabilityBody,
    user: User = Depends(RequireRole(THERAPIST)),
    db: Session = Depends(get_db),
):
    """登記每週可當診時段，供行政媒合時參考。"""
    for s in body.slots:
        if s.get("period") not in PERIODS or not (0 <= int(s.get("weekday", -1)) <= 6):
            raise HTTPException(status_code=400, detail=f"時段格式錯誤：{s}")

    db.query(TherapistAvailability).filter(
        TherapistAvailability.therapist_id == user.id
    ).delete()
    db.flush()
    seen = set()
    for s in body.slots:
        key = (int(s["weekday"]), s["period"])
        if key in seen:
            continue
        seen.add(key)
        db.add(TherapistAvailability(therapist_id=user.id, weekday=key[0], period=key[1]))
    write_audit(db, "therapist_availability", user.id, "UPDATE", user.id, None,
                {"slot_count": len(seen)})
    db.commit()
    return {"saved": len(seen)}


# ---------------------------------------------------------------------------
# 調整鐘點費（Q24：跳窗詢問套用範圍）
# ---------------------------------------------------------------------------
class BasePriceBody(BaseModel):
    base_price: float
    # new_only 僅新案適用／all_ongoing 套用到所有進行中個案
    scope: str


@router.put("/base-price")
def update_base_price(
    body: BasePriceBody,
    user: User = Depends(RequireRole(THERAPIST)),
    db: Session = Depends(get_db),
):
    """調整個人鐘點費。

    Q24：心智圖載明「有些心理師調漲是全部個案都漲，有的是舊案維持舊價」，
    兩種都存在，所以由心理師在調價時自行選擇套用範圍，並留稽核。
    """
    if body.scope not in ("new_only", "all_ongoing"):
        raise HTTPException(status_code=400, detail="scope 需為 new_only 或 all_ongoing")

    before = float(user.base_price) if user.base_price is not None else None
    user.base_price = body.base_price

    updated = 0
    if body.scope == "all_ongoing":
        # 套用到所有「已排定但尚未執行」的預約
        updated = (
            db.query(Appointment)
            .filter(
                Appointment.therapist_id == user.id,
                Appointment.status == "booked",
                Appointment.funding_source == "self_pay",
            )
            .update(
                {Appointment.amount: body.base_price, Appointment.hourly_rate: body.base_price},
                synchronize_session=False,
            )
        )

    write_audit(db, "users", user.id, "UPDATE", user.id,
                {"base_price": before},
                {"base_price": body.base_price, "scope": body.scope, "appointments_updated": updated})
    db.commit()
    return {
        "base_price": body.base_price,
        "scope": body.scope,
        "appointments_updated": updated,
        "note": (
            "已套用到所有進行中個案的未執行預約"
            if body.scope == "all_ongoing"
            else "僅新案適用，既有預約維持原價"
        ),
    }
