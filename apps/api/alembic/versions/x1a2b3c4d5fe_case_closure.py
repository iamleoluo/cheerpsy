"""cases 加結案/復案欄位

Revision ID: x1a2b3c4d5fe
Revises: w1a2b3c4d5fd
Create Date: 2026-05-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x1a2b3c4d5fe"
down_revision: Union[str, None] = "w1a2b3c4d5fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("closed_by", sa.Integer(), nullable=True))
    op.add_column("cases", sa.Column("closure_reason", sa.String(length=500), nullable=True))
    op.add_column("cases", sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("reopened_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_cases_closed_by_users", "cases", "users", ["closed_by"], ["id"],
    )
    op.create_foreign_key(
        "fk_cases_reopened_by_users", "cases", "users", ["reopened_by"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_cases_reopened_by_users", "cases", type_="foreignkey")
    op.drop_constraint("fk_cases_closed_by_users", "cases", type_="foreignkey")
    op.drop_column("cases", "reopened_by")
    op.drop_column("cases", "reopened_at")
    op.drop_column("cases", "closure_reason")
    op.drop_column("cases", "closed_by")
    op.drop_column("cases", "closed_at")
