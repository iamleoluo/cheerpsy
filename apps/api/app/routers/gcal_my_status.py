"""心理師自己的 Google 行事曆同步狀態（唯讀）。

只回「自己」的資料：診所是否已連上 Google、自己的行事曆是否建立並共享給自己的信箱、
最近一次推送成功時間、失敗／待推送筆數。失敗原因一律歸成簡短類別，
不回傳原始錯誤文字、token、其他心理師或個案的任何資料。
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.gcal import AppointmentGoogleEvent, GoogleCalendar, GoogleOAuthConnection
from app.models.appointment import Appointment
from app.models.user import User

router = APIRouter(prefix="/gcal", tags=["gcal"])


class MyGcalStatus(BaseModel):
    clinic_connected: bool  # 診所是否已連上 Google（授權有效）
    calendar_created: bool  # 自己的行事曆是否已建立
    shared_to_me: bool  # 是否已共享給自己的信箱
    share_email: str | None  # 自己的信箱（自己的資料）
    last_push_at: datetime | None  # 最近一次推送成功時間
    failed_count: int  # 失敗或被擋住、需要處理的筆數
    pending_count: int  # 待推送（含重試中）的筆數
    problem: str | None  # 簡短原因，沒有問題為 None


def short_reason(raw: str | None) -> str:
    """把原始錯誤摘要歸成簡短類別；不原樣回傳任何文字。"""
    t = raw or ""
    if any(k in t for k in ("無法連線", "網路", "逾時", "timeout")):
        return "網路問題，系統會自動重試"
    if "流量" in t:
        return "Google 流量限制，系統會自動重試"
    if any(k in t for k in ("找不到", "刪除")):
        return "行事曆在 Google 上找不到，請通知行政重建"
    if any(k in t for k in ("授權", "權限", "拒絕", "token", "401", "403")):
        return "權限問題，請通知管理員檢查 Google 連線"
    return "同步發生錯誤，請通知行政"


@router.get("/my-status", response_model=MyGcalStatus)
def my_status(user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    conn = db.get(GoogleOAuthConnection, 1)
    connected = conn is not None and conn.status == "active"
    cal = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == user.id).first()
    shared = cal is not None and cal.share_status in ("owner", "invited") and not cal.is_missing

    # 只算自己預約的 outbox 工作（outbox 以 appointment_id 對應預約，沒有外鍵）
    rows = db.execute(text("""
        SELECT o.status AS status, o.last_error AS last_error
          FROM gcal_outbox o JOIN appointments a ON a.id = o.appointment_id
         WHERE a.therapist_id = :tid AND o.status IN ('pending', 'running', 'retry', 'blocked', 'failed')
         ORDER BY o.updated_at DESC
    """), {"tid": user.id}).all()
    failed = [r for r in rows if r.status in ("failed", "blocked")]
    pending = [r for r in rows if r.status in ("pending", "running", "retry")]

    last_push = (
        db.query(func.max(AppointmentGoogleEvent.last_pushed_at))
        .join(Appointment, Appointment.id == AppointmentGoogleEvent.appointment_id)
        .filter(Appointment.therapist_id == user.id, AppointmentGoogleEvent.last_status == "pushed")
        .scalar()
    )

    problem = None
    if not connected:
        problem = ("Google 授權已失效，請通知管理員重新連結"
                   if conn is not None and conn.status == "token_invalid" else "診所尚未連上 Google")
    elif cal is None:
        problem = "你的行事曆尚未建立，請通知行政"
    elif cal.is_missing:
        problem = "行事曆在 Google 上找不到，請通知行政重建"
    elif cal.last_share_error:
        problem = short_reason(cal.last_share_error)
    elif failed:
        problem = short_reason(failed[0].last_error)

    return MyGcalStatus(
        clinic_connected=connected, calendar_created=cal is not None, shared_to_me=shared,
        share_email=user.gcal_share_email, last_push_at=last_push,
        failed_count=len(failed), pending_count=len(pending), problem=problem,
    )
