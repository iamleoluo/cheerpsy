"""appointments.couple_case_id (tag joint couple sessions)

Revision ID: z2a1b2c3d4e5
Revises: z1a2b3c4d5f0
Create Date: 2026-06-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "z2a1b2c3d4e5"
down_revision = "z1a2b3c4d5f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("couple_case_id", sa.Integer, sa.ForeignKey("cases.id"), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "couple_case_id")
