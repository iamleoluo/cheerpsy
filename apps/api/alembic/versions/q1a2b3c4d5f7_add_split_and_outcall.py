"""add session_records split + outcall fields

Revision ID: q1a2b3c4d5f7
Revises: p1a2b3c4d5f6
Create Date: 2026-05-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q1a2b3c4d5f7"
down_revision: Union[str, None] = "p1a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_records",
        sa.Column(
            "parent_record_id",
            sa.Integer(),
            sa.ForeignKey("session_records.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "session_records",
        sa.Column(
            "outcall_bonus",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "session_records",
        sa.Column("outcall_note", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_records", "outcall_note")
    op.drop_column("session_records", "outcall_bonus")
    op.drop_column("session_records", "parent_record_id")
