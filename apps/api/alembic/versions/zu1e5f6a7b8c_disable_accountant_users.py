"""會計（accountant）角色已刪除：既有 role='accountant' 的帳號改為停用

只把 users.is_active 設成 false：不刪資料列、不改成其他角色（歷史紀錄的建立者／經手人仍對得上）。
之後 API 不能再建立或改成 accountant，停用的 accountant 帳號也不能被重新啟用。

Revision ID: zu1e5f6a7b8c
Revises: zt0d4e5f6a7b
"""

import sqlalchemy as sa
from alembic import op

revision = "zu1e5f6a7b8c"
down_revision = "zt0d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE users SET is_active = false WHERE role = 'accountant'"))


def downgrade() -> None:
    # 資料不還原（不知道哪些帳號原本是啟用的）；不刪任何資料
    pass
