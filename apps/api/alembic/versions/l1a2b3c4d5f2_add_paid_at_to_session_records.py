"""add paid_at to session_records

Revision ID: l1a2b3c4d5f2
Revises: k1a2b3c4d5f1
Create Date: 2026-05-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l1a2b3c4d5f2"
down_revision: Union[str, None] = "k1a2b3c4d5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_records",
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing paid/claimed records: best-effort use session_date as payment date
    op.execute(
        """
        UPDATE session_records
        SET paid_at = (session_date::timestamp AT TIME ZONE 'UTC')
        WHERE payment_status IN ('paid', 'claimed') AND paid_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("session_records", "paid_at")
