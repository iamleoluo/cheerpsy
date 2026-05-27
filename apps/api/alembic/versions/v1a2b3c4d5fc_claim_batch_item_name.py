"""claim_batches 加 item_name（列印 PDF 時可編輯的服務項目名稱）

Revision ID: v1a2b3c4d5fc
Revises: u1a2b3c4d5fb
Create Date: 2026-05-27 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v1a2b3c4d5fc"
down_revision: Union[str, None] = "u1a2b3c4d5fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "claim_batches",
        sa.Column("item_name", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claim_batches", "item_name")
