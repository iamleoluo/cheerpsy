"""Phase 4: 財務日結、應收帳冊、月報表

新增 daily_closings（每日對帳，完成後鎖定）、monthly_reports（只存不可推導
的欄位）、supervisor_reviews（解鎖修改的主管覆核紀錄）；
therapist_payouts 拆五欄（月報表的心理師收入就是這張表的投影，
故從 Phase 6 提前到此）。

Revision ID: z7f1a2b3c4d9
Revises: z6e1f2a3b4c8
"""

import sqlalchemy as sa
from alembic import op

revision = "z7f1a2b3c4d9"
down_revision = "z6e1f2a3b4c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 每日對帳 ----------------------------------------------------------
    op.create_table(
        "daily_closings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        # pending 待對帳／closed 已完成對帳（鎖定）
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("cash_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("transfer_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unpaid_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("closing_date", name="uq_daily_closing_date"),
        sa.CheckConstraint("status IN ('pending','closed')", name="ck_daily_closing_status"),
    )
    op.add_column("session_records", sa.Column("daily_closing_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_session_records_daily_closing", "session_records", "daily_closings",
        ["daily_closing_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_session_records_daily_closing", "session_records", ["daily_closing_id"])

    # --- 月報表 ------------------------------------------------------------
    # 只存不可推導的欄位。已對帳天數、合計金額、心理師收入全部即時推導自
    # daily_closings（月份由 daily_closings.closing_date 推得），
    # 因此 session_records 刻意**不**掛 monthly_report_id。
    op.create_table(
        "monthly_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),  # YYYY-MM
        # draft 編製中／finalized 已定版
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", sa.Integer(), nullable=True),
        # 薪資發放日：結算月的隔月 25 日
        sa.Column("payout_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["finalized_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month", name="uq_monthly_report_month"),
        sa.CheckConstraint("status IN ('draft','finalized')", name="ck_monthly_report_status"),
    )

    # --- 主管覆核紀錄 -------------------------------------------------------
    # 對帳鎖定後解鎖修改才會進本表。補收款自動回寫、不視為修改、不列覆核。
    op.create_table(
        "supervisor_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("daily_closing_id", sa.Integer(), nullable=False),
        sa.Column("session_record_id", sa.Integer(), nullable=True),
        sa.Column("unlock_reason", sa.String(length=500), nullable=False),
        sa.Column("unlocked_by", sa.Integer(), nullable=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["daily_closing_id"], ["daily_closings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_record_id"], ["session_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unlocked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supervisor_reviews_closing", "supervisor_reviews", ["daily_closing_id"])

    # --- 心理師酬勞拆五欄（心智圖 §四.4）------------------------------------
    for col in ("counseling_income", "lecture_fee", "supervision_income", "venue_deduction"):
        op.add_column(
            "therapist_payouts",
            sa.Column(col, sa.Numeric(12, 2), nullable=False, server_default="0"),
        )
    # total_amount 已存在，作為五欄的合計；既有列以諮商收入回填
    op.execute("UPDATE therapist_payouts SET counseling_income = total_amount")

    # 酬勞明細可手動覆寫（Q22／Q23：不自動重算，人工調整並留稽核）
    op.add_column("payout_details", sa.Column("amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "payout_details",
        sa.Column("is_manually_adjusted", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "payout_details",
        sa.Column("rate_changed_flag", sa.Boolean(), nullable=False, server_default="false"),
    )

    # --- 補收款回寫月報表用 -------------------------------------------------
    op.add_column(
        "session_records",
        sa.Column("supplementary_paid_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_records", "supplementary_paid_at")
    op.drop_column("payout_details", "rate_changed_flag")
    op.drop_column("payout_details", "is_manually_adjusted")
    op.drop_column("payout_details", "amount")
    for col in ("venue_deduction", "supervision_income", "lecture_fee", "counseling_income"):
        op.drop_column("therapist_payouts", col)

    op.drop_index("ix_supervisor_reviews_closing", table_name="supervisor_reviews")
    op.drop_table("supervisor_reviews")
    op.drop_table("monthly_reports")

    op.drop_index("ix_session_records_daily_closing", table_name="session_records")
    op.drop_constraint("fk_session_records_daily_closing", "session_records", type_="foreignkey")
    op.drop_column("session_records", "daily_closing_id")
    op.drop_table("daily_closings")
