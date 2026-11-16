"""營運總覽。

帳務拆除上線 A：資料來源只有 appointments／cases／referral_requests，
不再讀 session_records、petty_cash，回應也沒有營收、未收、零用金欄位。
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.referral import ReferralRequest
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TZ = timezone(timedelta(hours=8))  # 診所在台灣
CHURN_DAYS = 45
PENDING_CHECKIN_DAYS = 30  # 「仍待報到」只回看這麼多天
OVERVIEW_ROLES = ("admin", "staff")  # 看得到全所媒合與流失統計


@router.get("")
def dashboard_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_therapist = user.role == "therapist"
    now = datetime.now(TZ)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    week_start = day_start - timedelta(days=day_start.weekday())  # 週一
    week_end = week_start + timedelta(days=7)
    month_start = day_start.replace(day=1)

    def appts(start: datetime, end: datetime):
        q = db.query(Appointment).filter(
            Appointment.status != "cancelled",
            Appointment.time_range.op("&&")(func.tstzrange(start, end)),
        )
        if is_therapist:
            q = q.filter(Appointment.therapist_id == user.id)
        return q

    today_q = appts(day_start, day_end)
    today_expected = today_q.count()
    today_arrived = today_q.filter(Appointment.checkin_status == "arrived").count()
    today_absent = today_q.filter(Appointment.checkin_status == "absent").count()
    week_appointments = appts(week_start, week_end).count()

    # 未來 7 天待提醒（已預約、尚未報到）
    reminder_q = db.query(func.count(Appointment.id)).filter(
        Appointment.status == "booked",
        Appointment.time_range.op("&&")(func.tstzrange(day_start, day_start + timedelta(days=7))),
    )
    if is_therapist:
        reminder_q = reminder_q.filter(Appointment.therapist_id == user.id)
    upcoming_reminders = reminder_q.scalar() or 0

    case_q = db.query(func.count(Case.id)).filter(Case.status.in_(["initial", "ongoing"]))
    if is_therapist:
        case_q = case_q.filter(Case.therapist_id == user.id)
    active_cases = case_q.scalar() or 0

    # 全所統計：心理師看不到
    new_referrals_month = matching_count = churn_count = None
    if user.role in OVERVIEW_ROLES:
        new_referrals_month = (
            db.query(func.count(ReferralRequest.id))
            .filter(ReferralRequest.created_at >= month_start)
            .scalar() or 0
        )
        matching_count = (
            db.query(func.count(ReferralRequest.id))
            .filter(ReferralRequest.status.in_(["new", "matching", "failed"]))
            .scalar() or 0
        )
        # 流失預警：進行中個案，最後一筆有效預約已結束超過 45 天（或從未有預約），且沒有未來預約
        cutoff = day_start - timedelta(days=CHURN_DAYS)
        recent = (
            db.query(Appointment.case_id)
            .filter(
                Appointment.case_id.isnot(None),
                Appointment.status.in_(["booked", "executed"]),
                text("upper(time_range) > :cutoff").bindparams(cutoff=cutoff),
            )
            .distinct()
            .scalar_subquery()
        )
        churn_count = (
            db.query(func.count(Case.id))
            .filter(Case.status.in_(["initial", "ongoing"]), ~Case.id.in_(recent))
            .scalar() or 0
        )

    return {
        "today_expected": today_expected,
        "today_arrived": today_arrived,
        "today_absent": today_absent,
        "week_appointments": week_appointments,
        "upcoming_reminders": upcoming_reminders,
        "active_cases": active_cases,
        "new_referrals_month": new_referrals_month,
        "matching_count": matching_count,
        "churn_count": churn_count,
    }


class PendingCheckinItem(BaseModel):
    appointment_id: int
    start_time: datetime
    end_time: datetime
    therapist_name: str | None
    subject_name: str | None  # 個案姓名；初診（尚無個案）為媒合需求表的姓名
    is_intake: bool
    session_type: str


class PendingCheckinOut(BaseModel):
    count: int
    items: list[PendingCheckinItem]


@router.get("/pending-checkin", response_model=PendingCheckinOut)
def pending_checkin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """開始時間早於今天 00:00（Asia/Taipei）、且在最近 30 天內、狀態仍為 booked 的預約：該補按「有到」或「未到」的。

    只看 [今天 00:00 往前 30 天, 今天 00:00)；更早的不列（也不算進 count）。從新排到舊。

    行政、管理員看全部；心理師只看自己的。只列出，不自動改任何狀態。
    """
    day_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.query(Appointment).filter(
        Appointment.status == "booked",
        func.lower(Appointment.time_range) < day_start,
        func.lower(Appointment.time_range) >= day_start - timedelta(days=PENDING_CHECKIN_DAYS),
    )
    if user.role == "therapist":
        q = q.filter(Appointment.therapist_id == user.id)
    elif user.role not in OVERVIEW_ROLES:
        return PendingCheckinOut(count=0, items=[])
    total = q.count()
    rows = q.order_by(func.lower(Appointment.time_range).desc()).limit(200).all()
    items = []
    for a in rows:
        ref = db.query(ReferralRequest).filter(ReferralRequest.id == a.referral_id).first() if a.referral_id else None
        items.append(PendingCheckinItem(
            appointment_id=a.id,
            start_time=a.time_range.lower.astimezone(TZ),  # 台北時間，前端取日期不會差一天
            end_time=a.time_range.upper.astimezone(TZ),
            therapist_name=a.therapist.name if a.therapist else None,
            subject_name=(a.case.name if a.case else (ref.name if ref else None)),
            is_intake=bool(a.is_intake),
            session_type=a.session_type,
        ))
    return PendingCheckinOut(count=total, items=items)
