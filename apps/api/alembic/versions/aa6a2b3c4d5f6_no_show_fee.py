"""機構未到補助：inst_plans.no_show_fee_numeric

見 V2升級計畫 09 §7.1（已裁示）：自費與大部分機構一律不做失約費，
NULL＝不補助（絕大多數方案的預設）；個別機構方案可設定補助金額，
報到「未到」時若命中，產生一筆可核銷的機構請款紀錄。

Revision ID: aa6a2b3c4d5f6
Revises: aa5a2b3c4d5f5
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "aa6a2b3c4d5f6"
down_revision = "aa5a2b3c4d5f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inst_plans", sa.Column("no_show_fee_numeric", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("inst_plans", "no_show_fee_numeric")
