"""add payment_method and payment_note to session_records

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-12 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("session_records", sa.Column("payment_method", sa.String(20), nullable=True))
    op.add_column("session_records", sa.Column("payment_note", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("session_records", "payment_note")
    op.drop_column("session_records", "payment_method")
