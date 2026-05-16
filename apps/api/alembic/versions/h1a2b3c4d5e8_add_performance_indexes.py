"""add performance indexes

Revision ID: h1a2b3c4d5e8
Revises: g1a2b3c4d5e7
Create Date: 2026-05-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "h1a2b3c4d5e8"
down_revision: Union[str, None] = "g1a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # session_records indexes for common queries
    op.create_index("ix_session_records_therapist_id", "session_records", ["therapist_id"])
    op.create_index("ix_session_records_session_date", "session_records", ["session_date"])
    op.create_index("ix_session_records_payment_status", "session_records", ["payment_status"])
    op.create_index("ix_session_records_claim_batch_id", "session_records", ["claim_batch_id"])
    op.create_index("ix_session_records_case_id", "session_records", ["case_id"])

    # appointments indexes
    op.create_index("ix_appointments_case_id", "appointments", ["case_id"])
    op.create_index("ix_appointments_therapist_id", "appointments", ["therapist_id"])
    op.create_index("ix_appointments_status", "appointments", ["status"])

    # cases indexes
    op.create_index("ix_cases_therapist_id", "cases", ["therapist_id"])
    op.create_index("ix_cases_status", "cases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cases_status")
    op.drop_index("ix_cases_therapist_id")
    op.drop_index("ix_appointments_status")
    op.drop_index("ix_appointments_therapist_id")
    op.drop_index("ix_appointments_case_id")
    op.drop_index("ix_session_records_case_id")
    op.drop_index("ix_session_records_claim_batch_id")
    op.drop_index("ix_session_records_payment_status")
    op.drop_index("ix_session_records_session_date")
    op.drop_index("ix_session_records_therapist_id")
