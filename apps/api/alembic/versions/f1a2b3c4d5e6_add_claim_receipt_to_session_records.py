"""add claim_number and receipt_number to session_records

Revision ID: f1a2b3c4d5e6
Revises: e4afc95f938e
Create Date: 2026-05-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e4afc95f938e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("session_records", sa.Column("claim_number", sa.String(100), nullable=True))
    op.add_column("session_records", sa.Column("receipt_number", sa.String(100), nullable=True))
    # Migrate old statuses
    op.execute("UPDATE session_records SET payment_status = 'unpaid' WHERE payment_status = 'pending_claim'")
    # Institution reconciled → claimed
    op.execute("""
        UPDATE session_records SET payment_status = 'claimed'
        WHERE payment_status = 'reconciled'
        AND case_id IN (SELECT id FROM cases WHERE funding_source = 'institution')
    """)
    # Self-pay reconciled → paid
    op.execute("""
        UPDATE session_records SET payment_status = 'paid'
        WHERE payment_status = 'reconciled'
    """)


def downgrade() -> None:
    op.execute("UPDATE session_records SET payment_status = 'pending_claim' WHERE payment_status = 'unpaid' AND claim_number IS NULL")
    op.execute("UPDATE session_records SET payment_status = 'reconciled' WHERE payment_status = 'claimed'")
    op.drop_column("session_records", "receipt_number")
    op.drop_column("session_records", "claim_number")
