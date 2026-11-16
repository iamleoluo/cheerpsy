"""rooms 加 is_active、sort_order（診間主檔維護）

只新增欄位，不刪表、不刪任何資料列。既有診間一律 is_active = true、sort_order = 0，
所以升級後畫面與預約行為都和升級前一樣；停用只能由系統管理員在 /admin 操作。

downgrade 只移除這兩個新欄位，不動任何診間或預約資料。

Revision ID: zi9e3f4a5b6e
Revises: zh8d2e3f4a5d
"""

import sqlalchemy as sa
from alembic import op

revision = "zi9e3f4a5b6e"
down_revision = "zh8d2e3f4a5d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("rooms", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("rooms", "sort_order")
    op.drop_column("rooms", "is_active")
