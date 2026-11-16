"""Google 日曆同步：診所設定與 OAuth 連線（docs/gcal-sync-plan.md §3.1、§3.2）。

兩張表都「固定只有一列」（id = 1），用 check constraint 保證。
refresh token 只存密文（見 app/services/secret_box.py），絕不寫入 log、回應或稽核紀錄。
"""

from sqlalchemy import (
    Numeric,
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base

TITLE_FORMATS = ("type_room", "type_room_code", "type_room_abbrev", "type_room_name")  # 計畫書的 (a)(b)(c)(d)
CONNECTION_STATUSES = ("active", "token_invalid", "disconnected")
# 心理師本人的分享狀態（行政名單的分享另看 shared_emails）：
# not_shared 沒信箱或尚未分享；invited 已送出 ACL（Google 不讓我們偵測對方是否已點加入）；
# owner 該信箱就是診所帳號，已是擁有者；unshared 離職或手動取消；error 最近一次同步失敗
SHARE_STATUSES = ("not_shared", "invited", "owner", "unshared", "error")


class ClinicSettings(Base):
    __tablename__ = "clinic_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_clinic_settings_single_row"),
        CheckConstraint(
            "event_title_format IN ('type_room', 'type_room_code', 'type_room_abbrev', 'type_room_name')",
            name="ck_clinic_settings_title_format",
        ),
    )

    id = Column(Integer, primary_key=True, default=1)
    # 預設 (d)：類型 · 診間 · 個案全名（診所已決定）。(a)(b)(c) 較保守，仍可選；縮寫規則見計畫書 §5
    event_title_format = Column(String(30), nullable=False, default="type_room_name", server_default="type_room_name")
    # 行政人員 Gmail 清單：每本日曆都以 reader 分享給名單上的人（診所帳號本人除外）
    staff_share_emails = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    push_therapist_notes_to_google = Column(Boolean, nullable=False, default=False, server_default="false")
    ical_follow_title_format = Column(Boolean, nullable=False, default=False, server_default="false")
    resync_lookback_days = Column(Integer, nullable=False, default=30, server_default="30")
    resync_lookahead_days = Column(Integer, nullable=False, default=180, server_default="180")
    # 失約費建議金額（應收提示，不產生流水）
    no_show_fee_advance_notice = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    no_show_fee_late_cancel = Column(Numeric(10, 2), nullable=False, default=200, server_default="200")
    no_show_fee_no_notice = Column(Numeric(10, 2), nullable=False, default=500, server_default="500")
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


class GoogleCalendar(Base):
    """每位心理師一本 Google 日曆（診所帳號擁有；docs/gcal-sync-plan.md §3.3）。"""

    __tablename__ = "google_calendars"
    __table_args__ = (
        UniqueConstraint("therapist_id", name="uq_google_calendars_therapist"),
        UniqueConstraint("google_calendar_id", name="uq_google_calendars_gid"),
        CheckConstraint(
            "share_status IN ('not_shared', 'invited', 'owner', 'unshared', 'error')",
            name="ck_google_calendars_share_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    google_calendar_id = Column(Text, nullable=False)  # calendarList.list 會 403，所以一定要自己存
    summary = Column(Text, nullable=False)
    # 上次同步完成後 Google 上的分享名單（不含擁有者）；只給畫面顯示，實際以 acl.list 為準
    shared_emails = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    share_status = Column(String(20), nullable=False, default="not_shared", server_default="not_shared")
    last_share_error = Column(Text, nullable=True)  # 給畫面看的摘要，不含 token
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")  # false＝凍結（離職／取消分享）
    is_missing = Column(Boolean, nullable=False, default=False, server_default="false")  # Google 上找不到（被手動刪除）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# 工作狀態：pending 待處理／running 處理中（工作者已領取）／retry 失敗等待重試／
# blocked 條件不足（未連結、沒有日曆…），補齊後可重排隊／done 完成／failed 重試用盡，需人工處理
OUTBOX_STATUSES = ("pending", "running", "retry", "blocked", "done", "failed")
OUTBOX_JOB_TYPES = ("upsert_event", "delete_event")


class AppointmentGoogleEvent(Base):
    """預約 ↔ Google 事件對應（一對一）。payload_hash 相同就不必再打 API（冪等）。"""

    __tablename__ = "appointment_google_events"

    # 刻意不設外鍵：預約可以被刪除（booked 狀態），刪除後仍要靠這裡的對應去 Google 刪掉事件
    appointment_id = Column(Integer, primary_key=True, autoincrement=False)
    google_calendar_id = Column(Text, nullable=False)
    google_event_id = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    last_pushed_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), nullable=False, default="pushed", server_default="pushed")  # pushed / deleted


class GcalOutbox(Base):
    """待推送到 Google 的工作。每個預約至多一列（dedupe_key = appt:{id}），重複 enqueue 只會把同一列重設為待處理。"""

    __tablename__ = "gcal_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_gcal_outbox_dedupe"),
        CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'blocked', 'done', 'failed')", name="ck_gcal_outbox_status"),
        CheckConstraint("job_type IN ('upsert_event', 'delete_event')", name="ck_gcal_outbox_job_type"),
        Index("ix_gcal_outbox_status_next", "status", "next_attempt_at"),
        Index("ix_gcal_outbox_appointment", "appointment_id"),
    )

    id = Column(Integer, primary_key=True)
    job_type = Column(String(20), nullable=False)  # 入列時依預約狀態決定；實際動作以工作者執行時重讀的預約為準
    appointment_id = Column(Integer, nullable=False)  # 不設外鍵，理由同 AppointmentGoogleEvent
    dedupe_key = Column(String(60), nullable=False)
    status = Column(String(10), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error = Column(Text, nullable=True)  # 給畫面看的摘要，不含 token 或個案資料
    # 每次 enqueue 加一。工作者處理完只有在版本沒變時才標 done，處理期間又有異動就維持待處理
    version = Column(Integer, nullable=False, default=1, server_default="1")
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
