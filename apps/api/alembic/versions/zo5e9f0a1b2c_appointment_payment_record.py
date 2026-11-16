"""預約：收款記錄（只記錄狀態、方式、時間、經手人）

payment_status：unpaid 未收／paid 已收／waived 免收。只是預約上的幾個欄位，
不產生 session_records、流水、核銷或對帳。只新增欄位，不刪表、不刪資料。

Revision ID: zo5e9f0a1b2c
Revises: zn4d8e9f0a1b
"""

import sqlalchemy as sa
from alembic import op

revision = "zo5e9f0a1b2c"
down_revision = "zn4d8e9f0a1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("payment_status", sa.String(10), nullable=False, server_default="unpaid"))
    op.add_column("appointments", sa.Column("payment_method", sa.String(20), nullable=True))
    op.add_column("appointments", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("paid_by", sa.Integer(), nullable=True))
    op.create_foreign_key("appointments_paid_by_fkey", "appointments", "users", ["paid_by"], ["id"], ondelete="SET NULL")
    op.create_check_constraint(
        "ck_appointments_payment_status", "appointments", "payment_status IN ('unpaid', 'paid', 'waived')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_payment_status", "appointments", type_="check")
    op.drop_constraint("appointments_paid_by_fkey", "appointments", type_="foreignkey")
    op.drop_column("appointments", "paid_by")
    op.drop_column("appointments", "paid_at")
    op.drop_column("appointments", "payment_method")
    op.drop_column("appointments", "payment_status")
