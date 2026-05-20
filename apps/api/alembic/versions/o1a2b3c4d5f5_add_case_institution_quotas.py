"""add case_institution_quotas table

Revision ID: o1a2b3c4d5f5
Revises: n1a2b3c4d5f4
Create Date: 2026-05-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o1a2b3c4d5f5"
down_revision: Union[str, None] = "n1a2b3c4d5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_institution_quotas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.Integer(),
            sa.ForeignKey("institutions.id"),
            nullable=False,
        ),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("total_count >= 0", name="ck_quota_total_nonneg"),
        sa.CheckConstraint("used_count >= 0", name="ck_quota_used_nonneg"),
        sa.CheckConstraint("used_count <= total_count", name="ck_quota_used_le_total"),
        sa.CheckConstraint("valid_from <= valid_until", name="ck_quota_period"),
    )
    op.create_index(
        "ix_quota_case_inst_until",
        "case_institution_quotas",
        ["case_id", "institution_id", "valid_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_quota_case_inst_until", table_name="case_institution_quotas")
    op.drop_table("case_institution_quotas")
