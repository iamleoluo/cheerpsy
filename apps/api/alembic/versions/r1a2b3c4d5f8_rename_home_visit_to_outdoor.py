"""rename session_type home_visit to outdoor

Revision ID: r1a2b3c4d5f8
Revises: q1a2b3c4d5f7
Create Date: 2026-05-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "r1a2b3c4d5f8"
down_revision: Union[str, None] = "q1a2b3c4d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE appointments SET session_type = 'outdoor' WHERE session_type = 'home_visit'")
    op.execute("UPDATE session_records SET session_type = 'outdoor' WHERE session_type = 'home_visit'")


def downgrade() -> None:
    op.execute("UPDATE appointments SET session_type = 'home_visit' WHERE session_type = 'outdoor'")
    op.execute("UPDATE session_records SET session_type = 'home_visit' WHERE session_type = 'outdoor'")
