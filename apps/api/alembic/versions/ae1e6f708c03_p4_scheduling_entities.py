"""P4 新排程實體：加時／視訊／請假欄位、行政流程提醒、場地租借、5F 雲燈教室

06 P4/P6 與 02 §1.2 列了這一整組，一直沒建。

場地租借跟 appointments 一樣佔用實體診間，所以也上一條 EXCLUDE USING GIST
擋自己表內的重疊；跨表（租借 vs 預約）沒辦法用單一約束表達，改由
app/services/room_occupancy.py 在應用層雙向檢查，並由 scripts/check_invariants.py
把「跨表不得重疊」列為守門條件。

雲燈教室刻意不掛 rooms：它是 5 樓的活動空間，不是定稿那 12 間診間之一，
掛進去會污染診間日曆、預約下拉與空間利用率報表。

Revision ID: ae1e6f708c03
Revises: ad0d5e6f7b02
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ae1e6f708c03"
down_revision = "ad0d5e6f7b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── appointments：加時 / 視訊 / 請假 ──────────────────────────────
    for col in (
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_adjusted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_adjusted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("duration_note", sa.String(200), nullable=True),
        sa.Column("video_link", sa.String(500), nullable=True),
        sa.Column("video_forwarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("video_forwarded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("leave_reason", sa.String(200), nullable=True),
        sa.Column("leave_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leave_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    ):
        op.add_column("appointments", col)

    # ── 行政流程提醒 ────────────────────────────────────────────────
    op.create_table(
        "appointment_admin_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.Integer(),
                  sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("side", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("done_by_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_tasks_appointment", "appointment_admin_tasks", ["appointment_id"])

    # ── 場地租借 ────────────────────────────────────────────────────
    op.create_table(
        "venue_rentals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rental_no", sa.String(30), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("time_range", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=True),
        sa.Column("renter_kind", sa.String(20), nullable=False, server_default="institution"),
        sa.Column("renter_name", sa.String(100), nullable=False),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("renter_therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("supervision_fee_mode", sa.String(1), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("payer", sa.String(20), nullable=False, server_default="renter"),
        sa.Column("attendance", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attended_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="booked"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_venue_rentals_rental_no", "venue_rentals", ["rental_no"])
    op.create_index("ix_venue_rentals_room", "venue_rentals", ["room_id"])
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE venue_rentals ADD CONSTRAINT excl_venue_room_time_overlap "
        "EXCLUDE USING GIST (room_id WITH =, time_range WITH &&) "
        "WHERE (status <> 'cancelled')"
    )

    # ── 5F 雲燈教室 ─────────────────────────────────────────────────
    op.create_table(
        "hall_bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("setup_range", postgresql.TSTZRANGE(), nullable=True),
        sa.Column("event_range", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("lecturer_kind", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("lecturer_therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("lecturer_name", sa.String(100), nullable=True),
        sa.Column("lecturer_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("fee_to_clinic_account", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("borrower", sa.String(100), nullable=True),
        sa.Column("attendee_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # 雲燈教室只有一間，活動時段本身不可重疊
    op.execute(
        "ALTER TABLE hall_bookings ADD CONSTRAINT excl_hall_event_overlap "
        "EXCLUDE USING GIST (event_range WITH &&) WHERE (status <> 'cancelled')"
    )


def downgrade() -> None:
    op.drop_table("hall_bookings")
    op.drop_table("venue_rentals")
    op.drop_index("ix_admin_tasks_appointment", table_name="appointment_admin_tasks")
    op.drop_table("appointment_admin_tasks")
    for name in ("leave_by", "leave_at", "leave_reason",
                 "video_forwarded_by", "video_forwarded_at", "video_link",
                 "duration_note", "duration_adjusted_by", "duration_adjusted_at",
                 "actual_end", "actual_start"):
        op.drop_column("appointments", name)
