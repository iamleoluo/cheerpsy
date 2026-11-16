"""Google 日曆同步 PR B：每位心理師一本日曆的對應表，與心理師的分享用 Gmail

只新增：表 google_calendars，以及 users.gcal_share_email（可為空）。
不改任何既有欄位、不刪資料。downgrade 只拿掉這兩樣。
（備註功能的 migration 另在 PR D，接在這支後面。）

Revision ID: zk1a5b6c7d8e
Revises: zj0f4a5b6c7d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "zk1a5b6c7d8e"
down_revision = "zj0f4a5b6c7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("gcal_share_email", sa.String(320), nullable=True))
    op.create_table(
        "google_calendars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("google_calendar_id", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("shared_emails", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("share_status", sa.String(20), nullable=False, server_default="not_shared"),
        sa.Column("last_share_error", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_missing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("therapist_id", name="uq_google_calendars_therapist"),
        sa.UniqueConstraint("google_calendar_id", name="uq_google_calendars_gid"),
        sa.CheckConstraint(
            "share_status IN ('not_shared', 'invited', 'owner', 'unshared', 'error')",
            name="ck_google_calendars_share_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("google_calendars")
    op.drop_column("users", "gcal_share_email")
