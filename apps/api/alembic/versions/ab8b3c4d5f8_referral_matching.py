"""媒合管理子系統：referrals / referral_batches / referral_batch_members

一個小的獨立子系統（09 §6 第 2 步）。媒合出第一次（初診）預約後即交棒
給既有的個案／預約系統，referrals 本身的資料就不再被讀取——見
document_reference/cheerpsy_v7_spec_extracted.md「媒合管理」。

Revision ID: ab8b3c4d5f8
Revises: aa7a2b3c4d5f7
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "ab8b3c4d5f8"
down_revision = "aa7a2b3c4d5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(10), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="in_person"),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("funding_note", sa.String(200), nullable=True),
        sa.Column("issues", sa.Text(), nullable=True),
        sa.Column("issue_note", sa.Text(), nullable=True),
        sa.Column("designated_therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("availability", sa.String(500), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("accepted_therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("converted_case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("close_reason", sa.String(500), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_referrals_referral_code", "referrals", ["referral_code"])
    op.create_index("ix_referrals_referral_code", "referrals", ["referral_code"])

    op.create_table(
        "referral_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referral_id", sa.Integer(), sa.ForeignKey("referrals.id"), nullable=False),
        sa.Column("batch_seq", sa.Integer(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_referral_batches_referral_id", "referral_batches", ["referral_id"])

    op.create_table(
        "referral_batch_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("referral_batches.id"), nullable=False),
        sa.Column("therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reply_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decline_reason", sa.String(50), nullable=True),
        sa.Column("proposed_slots", sa.Text(), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_referral_batch_members_batch_id", "referral_batch_members", ["batch_id"])
    op.create_index("ix_referral_batch_members_therapist_id", "referral_batch_members", ["therapist_id"])


def downgrade() -> None:
    op.drop_table("referral_batch_members")
    op.drop_table("referral_batches")
    op.drop_table("referrals")
