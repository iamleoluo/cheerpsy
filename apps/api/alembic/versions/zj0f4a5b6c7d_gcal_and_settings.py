"""Google 日曆同步：診所設定 clinic_settings 與 OAuth 連線 google_oauth_connections

只新增兩張表，不改任何既有表、不刪資料（docs/gcal-sync-plan.md §3）。
兩張表都固定只有一列（id = 1）。refresh token 只存密文。
downgrade 只 drop 這兩張新表。

Revision ID: zj0f4a5b6c7d
Revises: zi9e3f4a5b6e
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "zj0f4a5b6c7d"
down_revision = "zi9e3f4a5b6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_title_format", sa.String(30), nullable=False, server_default="type_room_abbrev"),
        sa.Column("staff_share_emails", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("push_therapist_notes_to_google", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ical_follow_title_format", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resync_lookback_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("resync_lookahead_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_clinic_settings_single_row"),
        sa.CheckConstraint(
            "event_title_format IN ('type_room', 'type_room_code', 'type_room_abbrev')",
            name="ck_clinic_settings_title_format",
        ),
    )
    op.create_table(
        "google_oauth_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("google_email", sa.String(320), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="disconnected"),
        sa.Column("token_invalid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("connected_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_google_oauth_single_row"),
        sa.CheckConstraint(
            "status IN ('active', 'token_invalid', 'disconnected')",
            name="ck_google_oauth_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("google_oauth_connections")
    op.drop_table("clinic_settings")
