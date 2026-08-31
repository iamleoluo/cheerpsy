"""移除 couple_members 相容 view

Phase 1b 更名 case_members 時建的過渡 view。ORM 的 CoupleMember 已直接
指向 case_members，全庫沒有其他 SQL 讀者，可以拆除。

session_records.receipt_no / product_sales.receipt_no **不在此拆除**：
它們存著歷史 R/P 格式收據號，且 data_import 仍以其比對既有資料。
應排在正式資料遷移（Stage 2）完成並核對後再處理。

Revision ID: zc3e6f7a8b9e
Revises: zb2d5e6f7a8d
"""

from alembic import op

revision = "zc3e6f7a8b9e"
down_revision = "zb2d5e6f7a8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS couple_members")


def downgrade() -> None:
    op.execute(
        "CREATE VIEW couple_members AS "
        "SELECT id, couple_case_id, member_case_id, role, created_at FROM case_members"
    )
