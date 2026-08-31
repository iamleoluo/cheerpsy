"""Phase 7：數據分析。

指標定義的來源與狀態：

  ✅ 定義明確，已實作
     到案率     ＝ 實際到案人次 ÷ 預約人次（未到與取消都算未到案）
     媒合成功率 ＝ 承接數 ÷ 被派案數
     黏著度     ＝ 依個案預約週期歸類（每週2次以上／每週1次／隔週1次／
                  每月1次／不固定）
     來源分析   ＝ 管道來源佔比
     主述議題   ＝ TOP N

  ⚠️ 定義未定，以預設值計算並在回應中標記 caveat
     留案率     自費滿 6 次／機構用罄後自費滿 3 次 —— 規則明確，
                但「累積次數」還是「該年度次數」未定，先用**累積**
     空間使用率 分母（營業時段）是否排除心理師未當診時段未定，
                先用**完整營業時段 08:00–22:00**

  ⏸️ 未實作
     目標達成率 目標收入／目標人次由誰設定、設在哪一層未定（Q18），
                因此不提供此指標，避免顯示沒有依據的數字
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.referral import ReferralDispatchTarget, ReferralRequest
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])

ADMIN_VIEW = ["admin", "accountant"]

# 營業時段 08:00–22:00，全年無休假設（Q19 待定）
BUSINESS_HOURS_PER_DAY = 14

# 留案認定（心智圖 §一.3）
SELF_PAY_RETENTION_SESSIONS = 6
INSTITUTION_FOLLOWUP_SESSIONS = 3


def _range(period: str, ref: date) -> tuple[date, date]:
    if period == "week":
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    if period == "quarter":
        q = (ref.month - 1) // 3
        start = date(ref.year, q * 3 + 1, 1)
        end_month = q * 3 + 3
        end = date(ref.year + (end_month == 12), (end_month % 12) + 1, 1) - timedelta(days=1)
        return start, end
    # month
    start = date(ref.year, ref.month, 1)
    end = date(ref.year + (ref.month == 12), (ref.month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def _adherence_bucket(gaps: list[int]) -> str:
    """依平均間隔天數歸類黏著度。"""
    if not gaps:
        return "不固定"
    avg = sum(gaps) / len(gaps)
    if avg <= 4:
        return "每週2次以上"
    if avg <= 10:
        return "每週1次"
    if avg <= 20:
        return "隔週1次"
    if avg <= 40:
        return "每月1次"
    return "不固定"


@router.get("")
def analytics(
    period: str = Query("month", pattern="^(week|month|quarter)$"),
    ref: date | None = Query(None, description="區間內任一天，預設今天"),
    therapist_id: int | None = Query(None),
    user: User = Depends(RequireRole(ADMIN_VIEW)),
    db: Session = Depends(get_db),
):
    start, end = _range(period, ref or date.today())
    return _build(db, start, end, therapist_id)


@router.get("/mine")
def my_analytics(
    period: str = Query("month", pattern="^(week|month|quarter)$"),
    ref: date | None = Query(None),
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    """心理師只看自己的數據，不與他人橫向比較（排名僅管理者可見）。"""
    start, end = _range(period, ref or date.today())
    out = _build(db, start, end, user.id)
    out["scope"] = "self"
    return out


def _build(db: Session, start: date, end: date, therapist_id: int | None) -> dict:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    appt_q = db.query(Appointment).filter(
        Appointment.time_range.op("&&")(func.tstzrange(start_dt, end_dt))
    )
    if therapist_id:
        appt_q = appt_q.filter(Appointment.therapist_id == therapist_id)
    appts = appt_q.all()

    # ── 到案率 ──────────────────────────────────────────────
    booked = [a for a in appts if a.status != "cancelled"]
    arrived = [a for a in booked if a.checkin_status == "arrived"]
    attendance_rate = round(len(arrived) / len(booked) * 100, 1) if booked else None

    # ── 空間使用率（⚠️ 分母未定，見檔頭）────────────────────
    room_count = db.query(func.count(Room.id)).scalar() or 0
    days = (end - start).days + 1
    capacity_hours = room_count * days * BUSINESS_HOURS_PER_DAY
    used_hours = 0.0
    for a in booked:
        if a.room_id and a.time_range:
            used_hours += (a.time_range.upper - a.time_range.lower).total_seconds() / 3600
    room_utilization = (
        round(used_hours / capacity_hours * 100, 1) if capacity_hours else None
    )

    # ── 媒合成功率 ──────────────────────────────────────────
    tgt_q = db.query(ReferralDispatchTarget)
    if therapist_id:
        tgt_q = tgt_q.filter(ReferralDispatchTarget.therapist_id == therapist_id)
    targets = tgt_q.all()
    responded = [t for t in targets if t.status in ("accepted", "declined")]
    accepted = [t for t in targets if t.status == "accepted"]
    match_rate = round(len(accepted) / len(targets) * 100, 1) if targets else None

    # ── 個案與留案率 ────────────────────────────────────────
    case_q = db.query(Case)
    if therapist_id:
        case_q = case_q.filter(Case.therapist_id == therapist_id)
    cases = case_q.all()
    ongoing = [c for c in cases if c.status == "ongoing"]

    rec_q = db.query(SessionRecord).filter(SessionRecord.is_void.is_(False))
    if therapist_id:
        rec_q = rec_q.filter(SessionRecord.therapist_id == therapist_id)
    all_records = rec_q.all()

    by_case: dict[int, list[SessionRecord]] = {}
    for r in all_records:
        if r.case_id:
            by_case.setdefault(r.case_id, []).append(r)

    retained = 0
    for c in ongoing:
        rs = sorted(by_case.get(c.id, []), key=lambda x: x.session_date)
        self_pay = [r for r in rs if r.funding_source != "institution"]
        inst = [r for r in rs if r.funding_source == "institution"]
        if inst:
            # 機構案：機構次數用完後，自費紀錄超過 3 次才算留案
            last_inst = inst[-1].session_date
            after = [r for r in self_pay if r.session_date > last_inst]
            if len(after) > INSTITUTION_FOLLOWUP_SESSIONS:
                retained += 1
        elif len(self_pay) >= SELF_PAY_RETENTION_SESSIONS:
            retained += 1
    retention_rate = round(retained / len(ongoing) * 100, 1) if ongoing else None

    # ── 黏著度分布 ──────────────────────────────────────────
    adherence = Counter()
    for c in ongoing:
        dates = sorted({r.session_date for r in by_case.get(c.id, [])})
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        adherence[_adherence_bucket(gaps)] += 1

    # ── 來源分析與主述議題 ──────────────────────────────────
    ref_rows = db.query(ReferralRequest).filter(
        ReferralRequest.created_at >= start_dt, ReferralRequest.created_at < end_dt
    ).all()
    sources = Counter((r.referral_source or "未填") for r in ref_rows)
    complaints = Counter(
        (r.chief_complaint or "").strip() for r in ref_rows if (r.chief_complaint or "").strip()
    )

    total_src = sum(sources.values())
    source_pct = [
        {"label": k, "count": v, "percent": round(v / total_src * 100, 1)}
        for k, v in sources.most_common()
    ] if total_src else []

    # ── 時段分析（早／午／晚）──────────────────────────────
    slot_counts = {"morning": 0, "afternoon": 0, "evening": 0}
    for a in booked:
        if not a.time_range:
            continue
        h = a.time_range.lower.astimezone().hour
        if h < 12:
            slot_counts["morning"] += 1
        elif h < 18:
            slot_counts["afternoon"] += 1
        else:
            slot_counts["evening"] += 1

    return {
        "period": {"start": start, "end": end, "days": days},
        "metrics": {
            "attendance_rate": attendance_rate,
            "booked_count": len(booked),
            "arrived_count": len(arrived),
            "room_utilization": room_utilization,
            "match_success_rate": match_rate,
            "match_dispatched": len(targets),
            "match_accepted": len(accepted),
            "match_responded": len(responded),
            "retention_rate": retention_rate,
            "retained_cases": retained,
            "ongoing_cases": len(ongoing),
        },
        "adherence": [{"label": k, "count": v} for k, v in adherence.most_common()],
        "sources": source_pct,
        "top_complaints": [
            {"label": k, "count": v} for k, v in complaints.most_common(5)
        ],
        "time_slots": slot_counts,
        # 前端據此在對應數字旁顯示說明，避免使用者誤以為定義已確定
        "caveats": {
            "retention_rate": (
                "留案率採「累積次數」計算（自費滿 6 次；機構案於額度用罄後"
                "自費超過 3 次）。「累積 vs 該年度」尚未定案。"
            ),
            "room_utilization": (
                f"分母採完整營業時段（{BUSINESS_HOURS_PER_DAY} 小時／日 × "
                f"{room_count} 間 × {days} 天）。是否應排除心理師未當診時段尚未定案。"
            ),
            "target_achievement": (
                "目標達成率未提供：目標收入／目標人次由誰設定、設在哪一層尚未定案，"
                "不顯示沒有依據的數字。"
            ),
        },
    }
