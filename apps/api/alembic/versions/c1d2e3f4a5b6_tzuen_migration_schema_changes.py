"""TzuEn migration: commission_rate, created_by, case numbering, claim_batches

Revision ID: c1d2e3f4a5b6
Revises: ee29ee750d68
Create Date: 2026-05-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "ee29ee750d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- users: commission_rate --
    op.add_column("users", sa.Column("commission_rate", sa.Numeric(4, 2), nullable=True))

    # -- cases: temp_seq, case_number, billing_cycle, created_by --
    op.execute("CREATE SEQUENCE IF NOT EXISTS cases_temp_seq_seq")
    op.add_column("cases", sa.Column("temp_seq", sa.Integer(), nullable=True))
    op.execute("UPDATE cases SET temp_seq = nextval('cases_temp_seq_seq') WHERE temp_seq IS NULL")
    op.add_column("cases", sa.Column("case_number", sa.String(10), nullable=True))
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    op.add_column("cases", sa.Column("billing_cycle", sa.String(20), nullable=False, server_default="once"))
    op.add_column("cases", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- appointments: visit_seq, created_by --
    op.add_column("appointments", sa.Column("visit_seq", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- institutions: code, created_by --
    op.add_column("institutions", sa.Column("code", sa.String(5), nullable=True))
    op.create_index("ix_institutions_code", "institutions", ["code"], unique=True)
    op.add_column("institutions", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- claim_batches (new table) --
    op.create_table(
        "claim_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_number", sa.String(50), unique=True, nullable=False),
        sa.Column("external_ref", sa.String(100), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(20), nullable=True),
        sa.Column("expected_sessions", sa.Integer(), nullable=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_note", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="collecting"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- session_records: commission_rate_used, claim_batch_id, therapist_doc, created_by --
    op.add_column("session_records", sa.Column("commission_rate_used", sa.Numeric(4, 2), nullable=True))
    op.add_column("session_records", sa.Column("claim_batch_id", sa.Integer(), sa.ForeignKey("claim_batches.id"), nullable=True))
    op.add_column("session_records", sa.Column("therapist_doc_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("session_records", sa.Column("therapist_doc_submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("session_records", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- invoices: created_by --
    op.add_column("invoices", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- therapist_payouts: created_by --
    op.add_column("therapist_payouts", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    # -- petty_cash: created_by --
    op.add_column("petty_cash", sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("petty_cash", "created_by")
    op.drop_column("therapist_payouts", "created_by")
    op.drop_column("invoices", "created_by")
    op.drop_column("session_records", "created_by")
    op.drop_column("session_records", "therapist_doc_submitted_by")
    op.drop_column("session_records", "therapist_doc_submitted_at")
    op.drop_column("session_records", "claim_batch_id")
    op.drop_column("session_records", "commission_rate_used")
    op.drop_table("claim_batches")
    op.drop_column("institutions", "created_by")
    op.drop_index("ix_institutions_code", "institutions")
    op.drop_column("institutions", "code")
    op.drop_column("appointments", "created_by")
    op.drop_column("appointments", "visit_seq")
    op.drop_column("cases", "created_by")
    op.drop_column("cases", "billing_cycle")
    op.drop_index("ix_cases_case_number", "cases")
    op.drop_column("cases", "case_number")
    op.drop_column("cases", "temp_seq")
    op.execute("DROP SEQUENCE IF EXISTS cases_temp_seq_seq")
    op.drop_column("users", "commission_rate")
