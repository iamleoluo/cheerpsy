"""預約與價目項目：consult_type（諮商型態）、service_type（服務型態）

計價時真的帶入價目挑選。只新增可為 NULL 的欄位，不動既有資料。
- appointments.consult_type：individual 個別／couple 伴侶／family 家族／parenting 親職
- appointments.service_type：沿用價目項目的服務型態代碼（individual、visitation、outreach_individual…）
- plan_rate_items.consult_type：NULL＝不限

Revision ID: zs9c3d4e5f6a
Revises: zr8b2c3d4e5f
"""

import sqlalchemy as sa
from alembic import op

revision = "zs9c3d4e5f6a"
down_revision = "zr8b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("consult_type", sa.String(20), nullable=True))
    op.add_column("appointments", sa.Column("service_type", sa.String(30), nullable=True))
    op.add_column("plan_rate_items", sa.Column("consult_type", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("plan_rate_items", "consult_type")
    op.drop_column("appointments", "service_type")
    op.drop_column("appointments", "consult_type")
