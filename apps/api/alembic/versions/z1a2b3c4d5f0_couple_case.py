"""couple case: case_type + couple_members

Revision ID: z1a2b3c4d5f0
Revises: y1a2b3c4d5ff
Create Date: 2026-06-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "z1a2b3c4d5f0"
down_revision = "y1a2b3c4d5ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("case_type", sa.String(20), nullable=False, server_default="individual"),
    )
    op.create_table(
        "couple_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("couple_case_id", sa.Integer, sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("member_case_id", sa.Integer, sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("couple_case_id", "member_case_id", name="uq_couple_member"),
    )


def downgrade() -> None:
    op.drop_table("couple_members")
    op.drop_column("cases", "case_type")
