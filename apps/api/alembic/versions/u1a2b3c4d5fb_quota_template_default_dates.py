"""quota_templates 加 default_valid_from / default_valid_until

Revision ID: u1a2b3c4d5fb
Revises: t1a2b3c4d5fa
Create Date: 2026-05-27 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u1a2b3c4d5fb"
down_revision: Union[str, None] = "t1a2b3c4d5fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quota_templates",
        sa.Column("default_valid_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "quota_templates",
        sa.Column("default_valid_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quota_templates", "default_valid_until")
    op.drop_column("quota_templates", "default_valid_from")
