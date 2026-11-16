"""機構方案：allows_zero_amount（借場地等允許金額 0 的方案）

預約金額必須大於 0，借場地方案例外。只新增欄位，預設 false（不改變既有行為）。

Revision ID: zr8b2c3d4e5f
Revises: zq7a1b2c3d4e
"""

import sqlalchemy as sa
from alembic import op

revision = "zr8b2c3d4e5f"
down_revision = "zq7a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institution_plans", sa.Column("allows_zero_amount", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("institution_plans", "allows_zero_amount")
