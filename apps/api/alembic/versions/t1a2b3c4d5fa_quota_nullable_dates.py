"""quota valid_from/valid_until 改為 nullable（None = 無時間上限）

Revision ID: t1a2b3c4d5fa
Revises: s1a2b3c4d5f9
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t1a2b3c4d5fa"
down_revision: Union[str, None] = "s1a2b3c4d5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "case_institution_quotas", "valid_from",
        existing_type=sa.Date(), nullable=True,
    )
    op.alter_column(
        "case_institution_quotas", "valid_until",
        existing_type=sa.Date(), nullable=True,
    )


def downgrade() -> None:
    # 復原前需先確保沒有 NULL 值（這裡不自動填補，避免破壞語意）
    op.alter_column(
        "case_institution_quotas", "valid_until",
        existing_type=sa.Date(), nullable=False,
    )
    op.alter_column(
        "case_institution_quotas", "valid_from",
        existing_type=sa.Date(), nullable=False,
    )
