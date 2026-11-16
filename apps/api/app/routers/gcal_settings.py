"""診所設定與 Google 連線（docs/gcal-sync-plan.md §6.1，PR A：只做連線與設定，尚未推送任何事件）。

權限：連結／解除連結／改設定只有 admin；admin、staff 可讀設定與同步健康狀態。
機密：authorization code、access／refresh token 不進回應、不進 log、不進稽核紀錄；
refresh token 只以 Fernet 密文存放（見 app/services/secret_box.py）。
"""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.config import settings
from app.database import get_db
from app.models.gcal import ClinicSettings, GoogleOAuthConnection
from app.models.user import User
from app.services import google_oauth, secret_box
from app.services.audit import write_audit

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("cheerpsy.gcal")

ADMIN = RequireRole(["admin"])
ADMIN_OR_STAFF = RequireRole(["admin", "staff"])

STATE_TTL_MINUTES = 10


# ---------------------------------------------------------------------------
# log 脫敏：uvicorn 的 access log 會印出完整請求網址，callback 的 ?code=…&state=… 不能留在 log 裡
# ---------------------------------------------------------------------------
class _RedactOAuthQuery(logging.Filter):
    _PATTERN = re.compile(r"([?&](?:code|state|scope)=)[^&\s\"']*")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._PATTERN.sub(r"\1[REDACTED]", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = self._PATTERN.sub(r"\1[REDACTED]", record.msg)
        return True


_redact_filter = _RedactOAuthQuery()
for _name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
    logging.getLogger(_name).addFilter(_redact_filter)


# ---------------------------------------------------------------------------
# 資料存取
# ---------------------------------------------------------------------------
def _settings_row(db: Session) -> ClinicSettings:
    row = db.get(ClinicSettings, 1)
    if row is None:
        row = ClinicSettings(id=1)
        db.add(row)
        db.flush()
    return row


def _connection_row(db: Session) -> GoogleOAuthConnection | None:
    return db.get(GoogleOAuthConnection, 1)


def _settings_snapshot(r: ClinicSettings) -> dict:
    return {
        "event_title_format": r.event_title_format,
        "staff_share_emails": list(r.staff_share_emails or []),
        "push_therapist_notes_to_google": r.push_therapist_notes_to_google,
        "ical_follow_title_format": r.ical_follow_title_format,
        "resync_lookback_days": r.resync_lookback_days,
        "resync_lookahead_days": r.resync_lookahead_days,
        "no_show_fee_advance_notice": float(r.no_show_fee_advance_notice),
        "no_show_fee_late_cancel": float(r.no_show_fee_late_cancel),
        "no_show_fee_no_notice": float(r.no_show_fee_no_notice),
    }


# ---------------------------------------------------------------------------
# 回應
# ---------------------------------------------------------------------------
class ConnectionOut(BaseModel):
    status: Literal["active", "token_invalid", "disconnected"]
    google_email: str | None = None
    scopes: list[str] = []
    connected_at: datetime | None = None
    last_success_at: datetime | None = None
    token_invalid_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    # 伺服器端環境變數是否齊全；不齊全時「連結」會回 503
    configured: bool
    missing_settings: list[str] = []


class ClinicSettingsOut(BaseModel):
    event_title_format: str
    staff_share_emails: list[str]
    push_therapist_notes_to_google: bool
    ical_follow_title_format: bool
    resync_lookback_days: int
    resync_lookahead_days: int
    no_show_fee_advance_notice: float
    no_show_fee_late_cancel: float
    no_show_fee_no_notice: float
    updated_at: datetime | None = None
    connection: ConnectionOut
    can_edit: bool


def _connection_out(conn: GoogleOAuthConnection | None) -> ConnectionOut:
    missing = google_oauth.missing_settings()
    if not secret_box.is_configured():
        missing = missing + ["GCAL_TOKEN_FERNET_KEY"]
    base = dict(configured=not missing, missing_settings=missing)
    if conn is None:
        return ConnectionOut(status="disconnected", **base)
    return ConnectionOut(
        status=conn.status,
        google_email=conn.google_email,
        scopes=(conn.scopes or "").split(),
        connected_at=conn.connected_at,
        last_success_at=conn.last_success_at,
        token_invalid_at=conn.token_invalid_at,
        last_error_code=conn.last_error_code,
        last_error_message=conn.last_error_message,
        **base,
    )  # 注意：refresh_token_enc 不在輸出欄位裡


def _settings_out(db: Session, user: User) -> ClinicSettingsOut:
    r = _settings_row(db)
    db.commit()
    return ClinicSettingsOut(
        **_settings_snapshot(r),
        updated_at=r.updated_at,
        connection=_connection_out(_connection_row(db)),
        can_edit=user.role == "admin",
    )


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
@router.get("/clinic", response_model=ClinicSettingsOut)
def get_clinic_settings(user: User = Depends(ADMIN_OR_STAFF), db: Session = Depends(get_db)):
    return _settings_out(db, user)


class ClinicSettingsPatch(BaseModel):
    # 行政分享名單不能從這裡改：必須走 PUT /settings/google/staff-emails，才會同步更新各日曆的分享
    model_config = ConfigDict(extra="forbid")

    event_title_format: Literal["type_room", "type_room_code", "type_room_abbrev", "type_room_name"] | None = None
    push_therapist_notes_to_google: bool | None = None
    ical_follow_title_format: bool | None = None
    resync_lookback_days: int | None = Field(None, ge=0, le=365)
    resync_lookahead_days: int | None = Field(None, ge=1, le=730)
    no_show_fee_advance_notice: float | None = Field(None, ge=0, le=99999)
    no_show_fee_late_cancel: float | None = Field(None, ge=0, le=99999)
    no_show_fee_no_notice: float | None = Field(None, ge=0, le=99999)


@router.get("/no-show-fees")
def get_no_show_fees(
    user: User = Depends(RequireRole(["admin", "staff", "accountant", "therapist"])),
    db: Session = Depends(get_db),
):
    """未到類型的建議失約費（應收提示）。各角色皆可讀，供未到視窗帶出建議金額。"""
    r = _settings_row(db)
    db.commit()
    return {
        "advance_notice": float(r.no_show_fee_advance_notice),
        "late_cancel": float(r.no_show_fee_late_cancel),
        "no_notice": float(r.no_show_fee_no_notice),
    }


@router.patch("/clinic", response_model=ClinicSettingsOut)
def patch_clinic_settings(
    body: ClinicSettingsPatch,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    row = _settings_row(db)
    before = _settings_snapshot(row)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None:
            continue  # 這些欄位都不可為 null；None 視為沒送
        setattr(row, k, v)
    row.updated_by_user_id = user.id
    write_audit(db, "clinic_settings", 1, "UPDATE", user.id, before, _settings_snapshot(row))
    db.commit()
    db.refresh(row)
    return _settings_out(db, user)


# ---------------------------------------------------------------------------
# Google 連線（OAuth）
# ---------------------------------------------------------------------------
def _state_key() -> str:
    # 與 access token 用不同的簽章金鑰：state token 不可能被當成登入 token 使用
    return f"{settings.JWT_SECRET}:gcal-oauth-state"


def _make_state(user: User) -> str:
    payload = {
        "purpose": "gcal_oauth",
        "sub": str(user.id),
        "nonce": secrets.token_urlsafe(8),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, _state_key(), algorithm=settings.JWT_ALGORITHM)


def _read_state(state: str | None) -> int | None:
    if not state:
        return None
    try:
        claims = jwt.decode(state, _state_key(), algorithms=[settings.JWT_ALGORITHM])
        if claims.get("purpose") != "gcal_oauth":
            return None
        return int(claims["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def _frontend_url() -> str:
    base = (settings.FRONTEND_URL or settings.CORS_ORIGINS.split(",")[0]).strip().rstrip("/")
    return base


def _back_to_admin(result: str) -> RedirectResponse:
    # 只帶結果代碼，不帶任何 token、code 或例外訊息
    return RedirectResponse(f"{_frontend_url()}/admin?{urlencode({'tab': 'calendar', 'gcal': result})}", status_code=302)


class ConnectOut(BaseModel):
    authorization_url: str


@router.post("/google/connect", response_model=ConnectOut)
def google_connect(user: User = Depends(ADMIN)):
    """開始 OAuth：回傳要把瀏覽器導過去的 Google 授權網址。"""
    if not secret_box.is_configured():
        raise HTTPException(status_code=503, detail="Google 連線尚未設定：缺少環境變數 GCAL_TOKEN_FERNET_KEY（或格式不正確）")
    try:
        client = google_oauth.get_client()
    except google_oauth.GoogleOAuthNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"Google 連線尚未設定：缺少環境變數 {'、'.join(e.missing)}") from None
    return ConnectOut(authorization_url=client.authorization_url(_make_state(user)))


@router.get("/google/callback")
def google_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Google 授權後導回這裡（瀏覽器直接跳轉，沒有 Authorization header，所以以簽章過的 state 辨識是哪位管理員）。"""
    user_id = _read_state(state)
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None or not user.is_active or user.role != "admin":
        return _back_to_admin("invalid_state")
    if error or not code:
        return _back_to_admin("denied")  # 使用者按了取消，或 Google 回錯誤

    try:
        client = google_oauth.get_client()
        tokens = client.exchange_code(code)
    except google_oauth.GoogleOAuthNotConfigured:
        return _back_to_admin("config_error")
    except google_oauth.GoogleOAuthError as e:
        logger.warning("gcal oauth: token exchange failed (%s)", e.code)  # 只記 Google 的錯誤碼
        return _back_to_admin("token_exchange_failed")

    granted = set(tokens.scope.split())
    if not set(google_oauth.CALENDAR_SCOPES) <= granted:
        # Google 允許使用者在同意畫面取消勾選個別權限；少一個就不能用，不要存半套授權
        return _back_to_admin("missing_scope")
    if not tokens.refresh_token:
        return _back_to_admin("no_refresh_token")
    try:
        encrypted = secret_box.encrypt(tokens.refresh_token)
    except secret_box.SecretBoxError:
        return _back_to_admin("config_error")

    now = datetime.now(timezone.utc)
    conn = _connection_row(db) or GoogleOAuthConnection(id=1)
    db.add(conn)
    conn.google_email = tokens.email
    conn.refresh_token_enc = encrypted
    conn.scopes = " ".join(sorted(granted))
    conn.status = "active"
    conn.token_invalid_at = None
    conn.last_success_at = now
    conn.last_error_code = None
    conn.last_error_message = None
    conn.connected_by_user_id = user.id
    conn.connected_at = now
    write_audit(db, "google_oauth_connections", 1, "CONNECT", user.id, None,
                {"google_email": conn.google_email, "scopes": conn.scopes})  # 不含任何 token
    db.commit()
    logger.info("gcal oauth: connected by user_id=%s", user.id)
    return _back_to_admin("connected")


@router.post("/google/disconnect", response_model=ConnectionOut)
def google_disconnect(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """解除連結：盡力向 Google 撤銷 token（失敗也繼續），清掉密文，狀態改 disconnected。"""
    conn = _connection_row(db)
    if conn is None or conn.status == "disconnected":
        return _connection_out(conn)
    revoked = False
    if conn.refresh_token_enc:
        try:
            token = secret_box.decrypt(conn.refresh_token_enc)
            google_oauth.get_client().revoke(token)
            revoked = True
        except (secret_box.SecretBoxError, google_oauth.GoogleOAuthNotConfigured, google_oauth.GoogleOAuthError):
            pass  # 撤銷失敗不擋本地清除（token 可能早已失效）
    conn.refresh_token_enc = None
    conn.status = "disconnected"
    conn.token_invalid_at = None
    conn.last_error_code = None
    conn.last_error_message = None
    write_audit(db, "google_oauth_connections", 1, "DISCONNECT", user.id,
                {"google_email": conn.google_email}, {"revoked_at_google": revoked})
    db.commit()
    db.refresh(conn)
    return _connection_out(conn)
