"""Google 日曆同步：診所設定與 OAuth 連線（docs/gcal-sync-plan.md §3.1、§3.2）。

兩張表都「固定只有一列」（id = 1），用 check constraint 保證。
refresh token 只存密文（見 app/services/secret_box.py），絕不寫入 log、回應或稽核紀錄。
"""

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base

TITLE_FORMATS = ("type_room", "type_room_code", "type_room_abbrev")  # 對應計畫書的 (a)、(b)、(c)
CONNECTION_STATUSES = ("active", "token_invalid", "disconnected")


class ClinicSettings(Base):
    __tablename__ = "clinic_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_clinic_settings_single_row"),
        CheckConstraint(
            "event_title_format IN ('type_room', 'type_room_code', 'type_room_abbrev')",
            name="ck_clinic_settings_title_format",
        ),
    )

    id = Column(Integer, primary_key=True, default=1)
    # 預設 (c)：類型 · 診間 · 姓名縮寫（診所已決定）。縮寫規則見計畫書 §5：不會輸出完整姓名
    event_title_format = Column(String(30), nullable=False, default="type_room_abbrev", server_default="type_room_abbrev")
    # 行政人員 Gmail 清單：每本日曆都以 reader 分享給名單上的人（診所帳號本人除外）
    staff_share_emails = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    push_therapist_notes_to_google = Column(Boolean, nullable=False, default=False, server_default="false")
    ical_follow_title_format = Column(Boolean, nullable=False, default=False, server_default="false")
    resync_lookback_days = Column(Integer, nullable=False, default=30, server_default="30")
    resync_lookahead_days = Column(Integer, nullable=False, default=180, server_default="180")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class GoogleOAuthConnection(Base):
    __tablename__ = "google_oauth_connections"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_google_oauth_single_row"),
        CheckConstraint(
            "status IN ('active', 'token_invalid', 'disconnected')",
            name="ck_google_oauth_status",
        ),
    )

    id = Column(Integer, primary_key=True, default=1)
    google_email = Column(String(320), nullable=True)
    refresh_token_enc = Column(Text, nullable=True)  # Fernet 密文；解除連結時清成 NULL
    scopes = Column(Text, nullable=False, default="", server_default="")  # 實際授權到的 scope，空白分隔
    status = Column(String(20), nullable=False, default="disconnected", server_default="disconnected")
    token_invalid_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(100), nullable=True)
    last_error_message = Column(Text, nullable=True)  # 給設定頁看的摘要，不得含 token
    connected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
