"""初診預約：case_id 可為空，改綁 referral_id

媒合「轉預約」時個案尚未建立（病歷號要等初診有到才產生），
因此初診預約無法有 case_id。改為：
  一般預約  → case_id NOT NULL
  初診預約  → referral_id NOT NULL、case_id 為空
初診有到後回填 case_id。

Revision ID: za1c4d5e6f7c
Revises: z9b3c4d5e6fb
"""

import sqlalchemy as sa
from alembic import op

revision = "za1c4d5e6f7c"
down_revision = "z9b3c4d5e6fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("appointments", "case_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("appointments", sa.Column("referral_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_referral", "appointments", "referral_requests",
        ["referral_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_appointments_referral", "appointments", ["referral_id"])
    # 兩者至少要有一個，避免出現既無個案也無媒合來源的孤兒預約
    op.create_check_constraint(
        "ck_appointments_case_or_referral",
        "appointments",
        "case_id IS NOT NULL OR referral_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_case_or_referral", "appointments", type_="check")
    op.drop_index("ix_appointments_referral", table_name="appointments")
    op.drop_constraint("fk_appointments_referral", "appointments", type_="foreignkey")
    op.drop_column("appointments", "referral_id")
    op.execute("DELETE FROM appointments WHERE case_id IS NULL")
    op.alter_column("appointments", "case_id", existing_type=sa.Integer(), nullable=False)
