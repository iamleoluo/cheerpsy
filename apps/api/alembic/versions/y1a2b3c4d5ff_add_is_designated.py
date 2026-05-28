"""add is_designated to cases

Revision ID: y1a2b3c4d5ff
Revises: x1a2b3c4d5fe
Create Date: 2026-05-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "y1a2b3c4d5ff"
down_revision = "x1a2b3c4d5fe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "is_designated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("cases", "is_designated")
