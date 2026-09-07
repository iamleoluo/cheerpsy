"""核銷案文件豁免：inst_claim_cases.docs_waived_at/docs_waived_by

從舊 claim_batches 移植過來的機制（見 services/claim_batch.py 的
apply_doc_waiver/revert_doc_waiver）。免繳文件的機構，行政一鍵把容器內
所有紀錄標記成視同已提交，不必等心理師一筆筆確認。

Revision ID: aa7a2b3c4d5f7
Revises: aa6a2b3c4d5f6
Create Date: 2026-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "aa7a2b3c4d5f7"
down_revision = "aa6a2b3c4d5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inst_claim_cases", sa.Column("docs_waived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inst_claim_cases", sa.Column("docs_waived_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("inst_claim_cases", "docs_waived_by")
    op.drop_column("inst_claim_cases", "docs_waived_at")
