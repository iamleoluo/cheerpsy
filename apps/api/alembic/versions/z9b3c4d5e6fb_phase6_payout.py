"""Phase 6: 心理師可當診時段

therapist_payouts 的五欄已於 Phase 4 提前建好，此處只補
therapist_availability（心智圖 §一.4：心理師提供每週看診時段）。

Revision ID: z9b3c4d5e6fb
Revises: z8a2b3c4d5ea
"""

import sqlalchemy as sa
from alembic import op

revision = "z9b3c4d5e6fb"
down_revision = "z8a2b3c4d5ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "therapist_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("therapist_id", sa.Integer(), nullable=False),
        # 0=週一 … 6=週日
        sa.Column("weekday", sa.Integer(), nullable=False),
        # morning 0800-1200／afternoon 1300-1700／evening 1800-2100
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["therapist_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("therapist_id", "weekday", "period", name="uq_therapist_availability"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_weekday"),
        sa.CheckConstraint(
            "period IN ('morning','afternoon','evening')", name="ck_availability_period"
        ),
    )
    op.create_index("ix_therapist_availability_therapist", "therapist_availability", ["therapist_id"])


def downgrade() -> None:
    op.drop_index("ix_therapist_availability_therapist", table_name="therapist_availability")
    op.drop_table("therapist_availability")
