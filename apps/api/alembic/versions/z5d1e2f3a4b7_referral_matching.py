"""Phase 2: 媒合管理

諮商需求表 → 派案（1–3 位、先回先得）→ 承接／婉拒 → 轉預約 → 初診有到
→ 產生病歷號並轉入個案管理。

純新增，不動任何既有表的語意。cases 只加 referral_id / dispatch_code /
chief_complaint / complaint_note 四個 nullable 欄位，既有匯入流程不受影響。

Revision ID: z5d1e2f3a4b7
Revises: z4c1d2e3f4a6
"""

import sqlalchemy as sa
from alembic import op

revision = "z5d1e2f3a4b7"
down_revision = "z4c1d2e3f4a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispatch_code", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("referral_source", sa.String(length=100), nullable=True),
        sa.Column("chief_complaint", sa.String(length=500), nullable=True),
        sa.Column("complaint_note", sa.Text(), nullable=True),
        sa.Column("consultation_mode", sa.String(length=30), nullable=False, server_default="individual"),
        sa.Column("partner_name", sa.String(length=100), nullable=True),
        sa.Column("funding_source", sa.String(length=20), nullable=False, server_default="self_pay"),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("cancel_reason", sa.String(length=40), nullable=True),
        sa.Column("cancel_note", sa.String(length=500), nullable=True),
        sa.Column("intake_appointment_id", sa.Integer(), nullable=True),
        sa.Column("intake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_show_reason", sa.String(length=500), nullable=True),
        sa.Column("case_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["institution_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["intake_appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_code", name="uq_referral_dispatch_code"),
        sa.CheckConstraint(
            "status IN ('new','matching','failed','converted','cancelled','closed','intake_done')",
            name="ck_referral_status",
        ),
        sa.CheckConstraint(
            "funding_source IN ('self_pay','institution')", name="ck_referral_funding"
        ),
    )
    op.create_index("ix_referral_requests_status", "referral_requests", ["status"])

    op.create_table(
        "referral_designations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_id", sa.Integer(), nullable=False),
        sa.Column("therapist_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["referral_id"], ["referral_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["therapist_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_id", "therapist_id", name="uq_referral_designation"),
    )
    op.create_index("ix_referral_designations_referral_id", "referral_designations", ["referral_id"])

    op.create_table(
        "referral_dispatches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["referral_id"], ["referral_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_id", "seq", name="uq_referral_dispatch_seq"),
        sa.CheckConstraint(
            "status IN ('open','accepted','failed','expired','cancelled')",
            name="ck_referral_dispatch_status",
        ),
    )
    op.create_index("ix_referral_dispatches_referral_id", "referral_dispatches", ["referral_id"])

    op.create_table(
        "referral_dispatch_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispatch_id", sa.Integer(), nullable=False),
        sa.Column("therapist_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("decline_reason", sa.String(length=40), nullable=True),
        sa.Column("decline_note", sa.String(length=500), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dispatch_id"], ["referral_dispatches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["therapist_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_id", "therapist_id", name="uq_referral_target"),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','taken','expired','released')",
            name="ck_referral_target_status",
        ),
        sa.CheckConstraint(
            "decline_reason IS NULL OR decline_reason IN "
            "('not_my_field','fully_booked','dual_relationship','other')",
            name="ck_referral_decline_reason",
        ),
    )
    op.create_index("ix_referral_targets_dispatch_id", "referral_dispatch_targets", ["dispatch_id"])
    op.create_index("ix_referral_targets_therapist_id", "referral_dispatch_targets", ["therapist_id"])

    op.create_table(
        "referral_slot_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("is_selected", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["target_id"], ["referral_dispatch_targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_id", "seq", name="uq_referral_slot_seq"),
        sa.CheckConstraint("seq BETWEEN 1 AND 3", name="ck_referral_slot_seq"),
    )
    op.create_index("ix_referral_slots_target_id", "referral_slot_offers", ["target_id"])

    # cases：追溯媒合來源（派案碼與病歷號並存）
    op.add_column("cases", sa.Column("referral_id", sa.Integer(), nullable=True))
    op.add_column("cases", sa.Column("dispatch_code", sa.String(length=12), nullable=True))
    op.add_column("cases", sa.Column("chief_complaint", sa.String(length=500), nullable=True))
    op.add_column("cases", sa.Column("complaint_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_cases_referral", "cases", "referral_requests",
        ["referral_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_cases_referral_id", "cases", ["referral_id"])


def downgrade() -> None:
    op.drop_index("ix_cases_referral_id", table_name="cases")
    op.drop_constraint("fk_cases_referral", "cases", type_="foreignkey")
    for col in ("complaint_note", "chief_complaint", "dispatch_code", "referral_id"):
        op.drop_column("cases", col)

    op.drop_table("referral_slot_offers")
    op.drop_table("referral_dispatch_targets")
    op.drop_table("referral_dispatches")
    op.drop_table("referral_designations")
    op.drop_index("ix_referral_requests_status", table_name="referral_requests")
    op.drop_table("referral_requests")
