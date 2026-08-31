"""名單制心理師：可被預約與派案，但沒有登入帳號

需求：系統應可新增心理師，他不需要新增帳號，但需要出現在
「可以預約」與「可以派案」的名單中。

作法：仍然是 users 的一列（appointments.therapist_id、referral
相關表、payouts 全部指向 users，不必改任何外鍵），只加一個
has_account 旗標。has_account=false 者：
  - 登入一律拒絕
  - 仍會出現在 /auth/therapists（可預約、可派案）
  - email 用內部保留網域避免與真人帳號衝突

Revision ID: zd4f7a8b9c1f
Revises: zc3e6f7a8b9e
"""

import sqlalchemy as sa
from alembic import op

revision = "zd4f7a8b9c1f"
down_revision = "zc3e6f7a8b9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("has_account", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE has_account = false")
    op.drop_column("users", "has_account")
