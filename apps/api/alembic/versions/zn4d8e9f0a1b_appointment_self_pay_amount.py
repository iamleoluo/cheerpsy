"""預約：自付額快照 self_pay_amount

預約建立時由方案價目算出「應收（amount）」與「個案自付額」並存成快照；之後改價目主檔不影響既有預約。
只新增欄位，不刪表、不刪資料。既有自費預約的自付額補成全額（amount），機構預約維持 0（舊資料沒有價目快照）。

Revision ID: zn4d8e9f0a1b
Revises: zm3c7d8e9f0a
"""

import sqlalchemy as sa
from alembic import op

revision = "zn4d8e9f0a1b"
down_revision = "zm3c7d8e9f0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("self_pay_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.execute("UPDATE appointments SET self_pay_amount = amount WHERE funding_source = 'self_pay'")


def downgrade() -> None:
    op.drop_column("appointments", "self_pay_amount")
