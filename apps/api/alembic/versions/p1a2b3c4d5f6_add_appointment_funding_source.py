"""add funding_source and quota_id to appointments

Revision ID: p1a2b3c4d5f6
Revises: o1a2b3c4d5f5
Create Date: 2026-05-20 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p1a2b3c4d5f6"
down_revision: Union[str, None] = "o1a2b3c4d5f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "funding_source",
            sa.String(length=20),
            nullable=False,
            server_default="self_pay",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "quota_id",
            sa.Integer(),
            sa.ForeignKey("case_institution_quotas.id"),
            nullable=True,
        ),
    )
    # Backfill existing booked/executed appointments from case.funding_source so
    # current behavior is preserved for in-flight records.
    op.execute(
        """
        UPDATE appointments AS a
        SET funding_source = COALESCE(c.funding_source, 'self_pay')
        FROM cases AS c
        WHERE a.case_id = c.id
        """
    )


def downgrade() -> None:
    op.drop_column("appointments", "quota_id")
    op.drop_column("appointments", "funding_source")
