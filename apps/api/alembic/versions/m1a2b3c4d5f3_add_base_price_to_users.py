"""add base_price to users

Revision ID: m1a2b3c4d5f3
Revises: l1a2b3c4d5f2
Create Date: 2026-05-18 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1a2b3c4d5f3"
down_revision: Union[str, None] = "l1a2b3c4d5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("base_price", sa.Numeric(10, 2), nullable=True),
    )
    # Sensible default for existing therapists
    op.execute(
        "UPDATE users SET base_price = 2000 WHERE role = 'therapist' AND base_price IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "base_price")
