"""心理師日曆對應與分享（docs/gcal-sync-plan.md §6.2，PR B：只建日曆與分享，尚未推送任何行程）。

權限：admin 與 staff 可管理心理師的日曆對應（填 Gmail、建立並分享、重寄邀請、取消分享）；
行政分享名單只有 admin 可改，staff 唯讀。心理師與會計一律 403。
Google 連線失敗或未連結時回 409（訊息可直接顯示給使用者）；Google 暫時出錯回 502。
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.gcal import ClinicSettings, GoogleCalendar
from app.models.user import User
from app.services import gcal_client, gcal_share
from app.services.audit import write_audit
from app.services.gcal_client import CalendarApiError, GcalNotConnected

router = APIRouter(prefix="/settings/google", tags=["settings"])
logger = logging.getLogger("cheerpsy.gcal")

ADMIN = RequireRole(["admin"])
ADMIN_OR_STAFF = RequireRole(["admin", "staff"])


# ---------------------------------------------------------------------------
# 回應
# ---------------------------------------------------------------------------
class CalendarOut(BaseModel):
    summary: str
    share_status: str
    shared_emails: list[str]
    last_share_error: str | None = None
    is_active: bool
    is_missing: bool
    updated_at: datetime | None = None


class TherapistRow(BaseModel):
    id: int
    name: str
    user_code: str | None = None
    has_account: bool
    is_active: bool
    share_email: str | None = None
    calendar: CalendarOut | None = None  # None＝尚未建立日曆


def _row_out(t: User, cal: GoogleCalendar | None) -> TherapistRow:
    return TherapistRow(
        id=t.id, name=t.name, user_code=t.user_code, has_account=t.has_account, is_active=t.is_active,
        share_email=t.gcal_share_email,
        calendar=None if cal is None else CalendarOut(
            summary=cal.summary, share_status=cal.share_status, shared_emails=list(cal.shared_emails or []),
            last_share_error=cal.last_share_error, is_active=cal.is_active, is_missing=cal.is_missing,
            updated_at=cal.updated_at),
    )


def _therapist(db: Session, therapist_id: int) -> User:
    t = db.query(User).filter(User.id == therapist_id, User.role == "therapist").first()
    if t is None:
        raise HTTPException(status_code=404, detail="找不到這位心理師")
    return t


def _calendar_of(db: Session, therapist_id: int) -> GoogleCalendar | None:
    return db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == therapist_id).first()


def _client(db: Session) -> gcal_client.CalendarClient:
    try:
        return gcal_client.get_calendar_client(db)
    except GcalNotConnected as e:
        raise HTTPException(status_code=409, detail=e.message) from None


def _google_down(e: CalendarApiError) -> HTTPException:
    logger.warning("gcal api error: HTTP %s %s", e.status, e.reason)
    return HTTPException(status_code=502, detail=gcal_share.describe_error(e))


def _snapshot(cal: GoogleCalendar | None) -> dict | None:
    if cal is None:
        return None
    return {"share_status": cal.share_status, "shared_emails": list(cal.shared_emails or []),
            "is_active": cal.is_active, "is_missing": cal.is_missing}


# ---------------------------------------------------------------------------
# 心理師對應表
# ---------------------------------------------------------------------------
@router.get("/therapists", response_model=list[TherapistRow])
def list_therapists(user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    """所有在職心理師，加上雖已離職但仍有日曆的人。不含任何個案資料。"""
    cals = {c.therapist_id: c for c in db.query(GoogleCalendar).all()}
    q = db.query(User).filter(User.role == "therapist")
    if cals:
        q = q.filter(or_(User.is_active.is_(True), User.id.in_(list(cals))))
    else:
        q = q.filter(User.is_active.is_(True))
    return [_row_out(t, cals.get(t.id)) for t in q.order_by(User.name, User.id).all()]


class EmailBody(BaseModel):
    email: str | None = Field(None, max_length=320)  # 空字串或 null＝清除

    @field_validator("email")
    @classmethod
    def _norm(cls, v):
        v = gcal_share.normalize_email(v)
        if v is not None and not gcal_share.EMAIL_RE.match(v):
            raise ValueError("email 格式不正確")
        return v


@router.put("/therapists/{therapist_id}/email", response_model=TherapistRow)
def set_share_email(
    therapist_id: int,
    body: EmailBody,
    user: User = Depends(ADMIN_OR_STAFF),
    db: Session = Depends(get_db),
):
    """設定／更改心理師的分享用 Gmail。已有日曆且已連結 Google 時，立刻同步：先取消舊信箱、再分享新信箱。
    尚未連結 Google 時只儲存，等建立日曆時才會分享。"""
    t = _therapist(db, therapist_id)
    if body.email:
        clash = db.query(User).filter(User.gcal_share_email == body.email, User.id != t.id,
                                      User.role == "therapist").first()
        if clash is not None:
            # 同一信箱填給兩位心理師，等於把 A 的日曆分享給 B
            raise HTTPException(status_code=409, detail=f"這個信箱已經是「{clash.name}」的分享信箱")
    cal = _calendar_of(db, t.id)
    before = {"gcal_share_email": t.gcal_share_email, "calendar": _snapshot(cal)}
    t.gcal_share_email = body.email
    db.flush()
    if cal is not None and not cal.is_missing:
        try:
            gcal_share.sync_calendar(db, _client(db), cal, t)
        except HTTPException:
            # 沒連結／授權失效：信箱照存，日曆標示尚未同步，連結恢復後按任一同步動作即可補上
            cal.share_status = "error"
            cal.last_share_error = "信箱已儲存，但尚未同步到 Google（Google 未連結或授權失效）"
    # 信箱欄位在 users 上，所以稽核記在 users（audit_log.operation 只有 10 字元）
    write_audit(db, "users", t.id, "UPDATE", user.id, before,
                {"gcal_share_email": t.gcal_share_email, "calendar": _snapshot(cal)})
    db.commit()
    return _row_out(t, cal)


@router.post("/therapists/{therapist_id}/provision", response_model=TherapistRow)
def provision_calendar(therapist_id: int, user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    """建立這位心理師的日曆（診所帳號擁有）並依「心理師 Gmail ∪ 行政名單」分享。可重複呼叫。"""
    t = db.query(User).filter(User.id == therapist_id, User.role == "therapist").with_for_update().first()
    if t is None:
        raise HTTPException(status_code=404, detail="找不到這位心理師")
    if not t.is_active:
        raise HTTPException(status_code=409, detail="這位心理師已離職，不建立新日曆")
    client = _client(db)
    before = _snapshot(_calendar_of(db, t.id))
    try:
        cal = gcal_share.provision(db, client, t)
    except gcal_share.GcalThrottled as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    except CalendarApiError as e:
        db.rollback()
        raise _google_down(e) from None
    write_audit(db, "google_calendars", cal.id, "PROVISION", user.id, before, _snapshot(cal))
    db.commit()
    return _row_out(t, cal)


@router.post("/therapists/{therapist_id}/resend-invite", response_model=TherapistRow)
def resend_invite(therapist_id: int, user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    t = _therapist(db, therapist_id)
    cal = _calendar_of(db, t.id)
    if cal is None or cal.is_missing:
        raise HTTPException(status_code=409, detail="這位心理師還沒有日曆，請先「建立並分享」")
    if not t.is_active or not cal.is_active:
        raise HTTPException(status_code=409, detail="這位心理師已離職或已取消分享，不能重寄邀請")
    mine = gcal_share.normalize_email(t.gcal_share_email)
    if not mine:
        raise HTTPException(status_code=409, detail="請先填寫這位心理師的分享用 Gmail")
    if mine == gcal_share.owner_email(db):
        raise HTTPException(status_code=409, detail="這個信箱就是診所帳號，已是日曆擁有者，不需邀請")
    client = _client(db)
    before = _snapshot(cal)
    gcal_share.resend_invite(db, client, cal, t)
    write_audit(db, "google_calendars", cal.id, "RESEND", user.id, before, _snapshot(cal))
    db.commit()
    return _row_out(t, cal)


@router.post("/therapists/{therapist_id}/unshare", response_model=TherapistRow)
def unshare_calendar(therapist_id: int, user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    """取消這位心理師本人的分享並凍結日曆（離職）。日曆保留；行政名單的分享不受影響。可重複呼叫。"""
    t = _therapist(db, therapist_id)
    cal = _calendar_of(db, t.id)
    if cal is None:
        raise HTTPException(status_code=404, detail="這位心理師還沒有日曆")
    if cal.is_missing:
        raise HTTPException(status_code=409, detail="Google 上找不到這本日曆，沒有東西可取消")
    client = _client(db)
    before = _snapshot(cal)
    gcal_share.unshare(db, client, cal, t)
    write_audit(db, "google_calendars", cal.id, "UNSHARE", user.id, before, _snapshot(cal))
    db.commit()
    return _row_out(t, cal)


# ---------------------------------------------------------------------------
# 行政分享名單
# ---------------------------------------------------------------------------
class StaffEmailsOut(BaseModel):
    emails: list[str]
    can_edit: bool
    owner_email: str | None = None  # 診所帳號本人不需要列入名單


class StaffEmailsBody(BaseModel):
    emails: list[str] = Field(max_length=50)

    @field_validator("emails")
    @classmethod
    def _emails(cls, v):
        out: list[str] = []
        for e in v:
            e = gcal_share.normalize_email(e)
            if not e or not gcal_share.EMAIL_RE.match(e):
                raise ValueError("email 格式不正確")
            if e not in out:
                out.append(e)
        return out


class StaffEmailsResult(StaffEmailsOut):
    synced: int = 0  # 已同步到 Google 的日曆本數
    failed: int = 0
    note: str | None = None


def _settings_row(db: Session) -> ClinicSettings:
    row = db.get(ClinicSettings, 1)
    if row is None:
        row = ClinicSettings(id=1)
        db.add(row)
        db.flush()
    return row


@router.get("/staff-emails", response_model=StaffEmailsOut)
def get_staff_emails(user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    return StaffEmailsOut(emails=gcal_share.staff_emails(db), can_edit=user.role == "admin",
                          owner_email=gcal_share.owner_email(db))


@router.put("/staff-emails", response_model=StaffEmailsResult)
def put_staff_emails(body: StaffEmailsBody, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """儲存行政分享名單，並對所有日曆重算「心理師 Gmail ∪ 行政名單 − 擁有者」、只寫差集。
    還沒連結 Google 時只儲存。個別日曆同步失敗不會讓儲存失敗，結果在 failed 與各日曆的狀態。"""
    row = _settings_row(db)
    before = {"staff_share_emails": list(row.staff_share_emails or [])}
    row.staff_share_emails = body.emails
    row.updated_by_user_id = user.id
    write_audit(db, "clinic_settings", 1, "UPDATE", user.id, before, {"staff_share_emails": body.emails})
    db.commit()

    result = StaffEmailsResult(emails=body.emails, can_edit=True, owner_email=gcal_share.owner_email(db))
    if db.query(GoogleCalendar).count() == 0:
        return result
    try:
        client = gcal_client.get_calendar_client(db)
    except GcalNotConnected as e:
        result.note = f"名單已儲存，但尚未同步到 Google：{e.message}"
        return result
    result.synced, result.failed = gcal_share.sync_all(db, client)
    return result
