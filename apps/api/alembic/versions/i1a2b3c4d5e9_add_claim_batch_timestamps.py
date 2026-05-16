"""add claim batch status timestamps

Revision ID: i1a2b3c4d5e9
Revises: h1a2b3c4d5e8
Create Date: 2026-05-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i1a2b3c4d5e9"
down_revision: Union[str, None] = "h1a2b3c4d5e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claim_batches", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claim_batches", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claim_batches", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("claim_batches", "closed_at")
    op.drop_column("claim_batches", "received_at")
    op.drop_column("claim_batches", "submitted_at")
