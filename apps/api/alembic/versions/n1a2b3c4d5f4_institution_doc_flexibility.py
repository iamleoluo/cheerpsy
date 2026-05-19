"""institution doc flexibility

Revision ID: n1a2b3c4d5f4
Revises: m1a2b3c4d5f3
Create Date: 2026-05-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n1a2b3c4d5f4"
down_revision: Union[str, None] = "m1a2b3c4d5f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column(
            "requires_therapist_docs",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "claim_batches",
        sa.Column("docs_waived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "claim_batches",
        sa.Column(
            "docs_waived_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("claim_batches", "docs_waived_by")
    op.drop_column("claim_batches", "docs_waived_at")
    op.drop_column("institutions", "requires_therapist_docs")
