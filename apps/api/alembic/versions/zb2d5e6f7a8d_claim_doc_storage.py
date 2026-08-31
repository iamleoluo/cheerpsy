"""核銷附件實際存檔

claim_documents 補上檔案儲存欄位。檔案存在 api 容器的
/data/claim_docs volume，DB 只記路徑與中繼資料。

Revision ID: zb2d5e6f7a8d
Revises: za1c4d5e6f7c
"""

import sqlalchemy as sa
from alembic import op

revision = "zb2d5e6f7a8d"
down_revision = "za1c4d5e6f7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claim_documents", sa.Column("stored_path", sa.String(length=500), nullable=True))
    op.add_column("claim_documents", sa.Column("content_type", sa.String(length=100), nullable=True))
    op.add_column("claim_documents", sa.Column("size_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("claim_documents", "size_bytes")
    op.drop_column("claim_documents", "content_type")
    op.drop_column("claim_documents", "stored_path")
