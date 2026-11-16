"""失約費設定：存在 clinic_settings，只作為「應收提示」

未到時帶出建議金額，行政可改或免收；不產生流水或核銷。只新增欄位。

Revision ID: zp6f0a1b2c3d
Revises: zo5e9f0a1b2c
"""

import sqlalchemy as sa
from alembic import op

revision = "zp6f0a1b2c3d"
down_revision = "zo5e9f0a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinic_settings", sa.Column("no_show_fee_advance_notice", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("clinic_settings", sa.Column("no_show_fee_late_cancel", sa.Numeric(10, 2), nullable=False, server_default="200"))
    op.add_column("clinic_settings", sa.Column("no_show_fee_no_notice", sa.Numeric(10, 2), nullable=False, server_default="500"))


def downgrade() -> None:
    op.drop_column("clinic_settings", "no_show_fee_no_notice")
    op.drop_column("clinic_settings", "no_show_fee_late_cancel")
    op.drop_column("clinic_settings", "no_show_fee_advance_notice")
