"""配號計數器：number_sequences

06 P0 排定、08 §6 列為第一項缺口的那支。取代散落各處的 COUNT(*)+1，
讓編號併發安全、不重發、而且可以配「指定日期」的號（灌歷史資料需要）。

不需要回填：app/services/numbering.py 第一次碰到某個 scope 時會自己從
既有資料算出起點，所以掛到既有資料庫上不會從 1 重來。

Revision ID: ac9c4d5e6a01
Revises: ab8b3c4d5f8
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "ac9c4d5e6a01"
down_revision = "ab8b3c4d5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "number_sequences",
        sa.Column("scope", sa.String(120), primary_key=True),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("number_sequences")
