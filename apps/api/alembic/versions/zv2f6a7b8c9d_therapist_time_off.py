"""新增 therapist_time_off（心理師「這段不接案」）

只新增一張表，不改任何既有表、不動既有資料。
預約落在請假時段會被擋下（409）；原因只有本人與行政看得到。

Revision ID: zv2f6a7b8c9d
Revises: zu1e5f6a7b8c
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSTZRANGE

revision = "zv2f6a7b8c9d"
down_revision = "zu1e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "therapist_time_off",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("therapist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("time_range", TSTZRANGE(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_therapist_time_off_therapist_id", "therapist_time_off", ["therapist_id"])
    op.execute("CREATE INDEX ix_therapist_time_off_range ON therapist_time_off USING gist (time_range)")


def downgrade() -> None:
    op.drop_table("therapist_time_off")
