"""rename therapist_code to user_code

Revision ID: j1a2b3c4d5f0
Revises: i1a2b3c4d5e9
Create Date: 2026-05-16 00:00:00.000000

"""
from alembic import op

revision = "j1a2b3c4d5f0"
down_revision = "i1a2b3c4d5e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "therapist_code", new_column_name="user_code")
    op.alter_column("invitations", "therapist_code", new_column_name="user_code")


def downgrade() -> None:
    op.alter_column("users", "user_code", new_column_name="therapist_code")
    op.alter_column("invitations", "user_code", new_column_name="therapist_code")
