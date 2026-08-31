"""活動／場地借用（5F 雲燈教室）與 iCal 訂閱

活動的**登記與空間佔用**規則明確，先實作；
**講師費的財務歸屬**（是否入慈恩帳戶、是否酌收行政服務費）待機構案
完整設計定案，故相關欄位建好但不進入任何財務計算。

Revision ID: ze5a8b9c1d2a
Revises: zd4f7a8b9c1f
"""

import sqlalchemy as sa
from alembic import op

revision = "ze5a8b9c1d2a"
down_revision = "zd4f7a8b9c1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("speaker", sa.String(length=200), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=True),
        # 活動時間
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        # 場佈時間（會一併佔用空間）
        sa.Column("setup_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("setup_end_at", sa.DateTime(timezone=True), nullable=True),
        # 借用人：therapist 心理師／staff 行政／external 外部講師
        sa.Column("borrower_type", sa.String(length=20), nullable=False),
        sa.Column("borrower_user_id", sa.Integer(), nullable=True),
        sa.Column("borrower_name", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        # ── 講師費：欄位先建，財務歸屬待定（Q16／Q17）──────────────
        sa.Column("has_lecture_fee", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("lecture_hourly_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("lecture_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("lecture_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["borrower_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "borrower_type IN ('therapist','staff','external')", name="ck_events_borrower_type"
        ),
        sa.CheckConstraint("end_at > start_at", name="ck_events_time_order"),
    )
    op.create_index("ix_events_start", "events", ["start_at"])
    op.create_index("ix_events_room", "events", ["room_id"])

    # 心理師的 iCal 訂閱 token（單向匯出到 Google 日曆，不需 OAuth）
    op.add_column("users", sa.Column("ical_token", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_ical_token", "users", ["ical_token"])


def downgrade() -> None:
    op.drop_constraint("uq_users_ical_token", "users", type_="unique")
    op.drop_column("users", "ical_token")
    op.drop_index("ix_events_room", table_name="events")
    op.drop_index("ix_events_start", table_name="events")
    op.drop_table("events")
