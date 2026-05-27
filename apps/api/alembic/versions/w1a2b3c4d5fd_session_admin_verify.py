"""session_records 加 admin_verified_at / admin_verified_by

Revision ID: w1a2b3c4d5fd
Revises: v1a2b3c4d5fc
Create Date: 2026-05-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w1a2b3c4d5fd"
down_revision: Union[str, None] = "v1a2b3c4d5fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_records",
        sa.Column("admin_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_records",
        sa.Column("admin_verified_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_session_records_admin_verified_by_users",
        "session_records",
        "users",
        ["admin_verified_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_session_records_admin_verified_by_users",
        "session_records",
        type_="foreignkey",
    )
    op.drop_column("session_records", "admin_verified_by")
    op.drop_column("session_records", "admin_verified_at")
