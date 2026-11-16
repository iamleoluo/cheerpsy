"""Google 日曆同步 PR C：預約事件對應表與 outbox

只新增兩張表：appointment_google_events、gcal_outbox。不改任何既有表、不刪資料。
downgrade 只 drop 這兩張。

Revision ID: zl2b6c7d8e9f
Revises: zk1a5b6c7d8e
"""

import sqlalchemy as sa
from alembic import op

revision = "zl2b6c7d8e9f"
down_revision = "zk1a5b6c7d8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointment_google_events",
        # 刻意不設外鍵：預約可被刪除，刪除後仍要靠對應去 Google 刪事件
        sa.Column("appointment_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("google_calendar_id", sa.Text(), nullable=False),
        sa.Column("google_event_id", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=False, server_default="pushed"),
    )
    op.create_table(
        "gcal_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(60), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_gcal_outbox_dedupe"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'blocked', 'done', 'failed')", name="ck_gcal_outbox_status"),
        sa.CheckConstraint("job_type IN ('upsert_event', 'delete_event')", name="ck_gcal_outbox_job_type"),
    )
    op.create_index("ix_gcal_outbox_status_next", "gcal_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_gcal_outbox_appointment", "gcal_outbox", ["appointment_id"])


def downgrade() -> None:
    op.drop_table("gcal_outbox")
    op.drop_table("appointment_google_events")
