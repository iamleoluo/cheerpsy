"""Notifications API — system-wide notification feed for all roles."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.notification import Notification
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str | None
    link: str | None
    is_read: bool
    created_at: datetime


class NotificationSummary(BaseModel):
    unread_count: int
    notifications: list[NotificationResponse]
    # Live computed alerts (not stored in DB)
    live_alerts: list[dict]


@router.get("", response_model=NotificationSummary)
def get_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get notifications + live computed alerts for the current user."""
    # Stored notifications (last 50)
    stored = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )

    unread_count = sum(1 for n in stored if not n.is_read)

    notifications = [
        NotificationResponse(
            id=n.id,
            type=n.type,
            title=n.title,
            message=n.message,
            link=n.link,
            is_read=n.is_read,
            created_at=n.created_at,
        )
        for n in stored
    ]

    # Live alerts computed on-the-fly
    live_alerts = _compute_live_alerts(user, db)

    return NotificationSummary(
        unread_count=unread_count + len(live_alerts),
        notifications=notifications,
        live_alerts=live_alerts,
    )


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user.id,
    ).first()
    if not n:
        raise HTTPException(status_code=404, detail="Not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.put("/read-all")
def mark_all_read(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read == False,  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"ok": True}


def _compute_live_alerts(user: User, db: Session) -> list[dict]:
    """Compute real-time alerts based on current data state."""
    alerts = []
    today = date.today()

    if user.role == "therapist":
        # 1. Today's appointments
        from sqlalchemy import cast, Date
        today_appts = (
            db.query(Appointment)
            .filter(
                Appointment.therapist_id == user.id,
                Appointment.status == "booked",
                cast(Appointment.start_time, Date) == today,
            )
            .count()
        )
        if today_appts > 0:
            alerts.append({
                "type": "appointment_today",
                "title": f"今日有 {today_appts} 場預約",
                "link": "/calendar",
                "severity": "info",
            })

        # 2. Pending doc confirmations (for institution claims)
        pending_docs = (
            db.query(SessionRecord)
            .filter(
                SessionRecord.therapist_id == user.id,
                SessionRecord.claim_batch_id.isnot(None),
                SessionRecord.therapist_doc_submitted_at.is_(None),
            )
            .count()
        )
        if pending_docs > 0:
            alerts.append({
                "type": "doc_pending",
                "title": f"有 {pending_docs} 筆諮商紀錄待確認提交",
                "link": "/claims",
                "severity": "warning",
            })

    elif user.role in ("admin", "staff"):
        # 1. Unpaid records not in any claim batch
        unpaid_no_batch = (
            db.query(SessionRecord)
            .filter(
                SessionRecord.payment_status == "unpaid",
                SessionRecord.claim_batch_id.is_(None),
            )
            .count()
        )
        if unpaid_no_batch > 0:
            alerts.append({
                "type": "payment_due",
                "title": f"{unpaid_no_batch} 筆帳單未收款且未建核銷案",
                "link": "/ledger?tab=pending",
                "severity": "warning",
            })

        # 2. Today's appointments (all)
        from sqlalchemy import cast, Date
        today_total = (
            db.query(Appointment)
            .filter(
                Appointment.status == "booked",
                cast(Appointment.start_time, Date) == today,
            )
            .count()
        )
        if today_total > 0:
            alerts.append({
                "type": "appointment_today",
                "title": f"今日共 {today_total} 場預約",
                "link": "/calendar",
                "severity": "info",
            })

        # 3. Claim batches in collecting (waiting for therapist docs)
        from app.models.claim_batch import ClaimBatch
        collecting = db.query(ClaimBatch).filter(ClaimBatch.status == "collecting").count()
        if collecting > 0:
            alerts.append({
                "type": "claim_collecting",
                "title": f"{collecting} 個核銷案等待心理師確認文件",
                "link": "/claims?status=collecting",
                "severity": "info",
            })

    elif user.role == "accountant":
        # Claim batches ready for review
        from app.models.claim_batch import ClaimBatch
        ready = db.query(ClaimBatch).filter(ClaimBatch.status.in_(["ready", "submitted"])).count()
        if ready > 0:
            alerts.append({
                "type": "claim_ready",
                "title": f"{ready} 個核銷案待審核/確認收款",
                "link": "/claims?status=ready",
                "severity": "info",
            })

    return alerts
