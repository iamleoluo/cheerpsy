"""restructure ledger and add product_sales

Revision ID: k1a2b3c4d5f1
Revises: j1a2b3c4d5f0
Create Date: 2026-05-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1a2b3c4d5f1"
down_revision: Union[str, None] = "j1a2b3c4d5f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── session_records: new columns ──────────────────────────────
    op.add_column("session_records", sa.Column("funding_source", sa.String(20), nullable=True))
    op.add_column("session_records", sa.Column("receipt_no", sa.String(30), nullable=True))
    op.add_column(
        "session_records",
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column("session_records", sa.Column("discount_note", sa.String(200), nullable=True))
    op.add_column(
        "session_records",
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("session_records", sa.Column("void_reason", sa.String(200), nullable=True))
    op.add_column(
        "session_records", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "session_records",
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    # Backfill funding_source from cases
    op.execute(
        """
        UPDATE session_records sr
        SET funding_source = c.funding_source
        FROM cases c
        WHERE sr.case_id = c.id AND sr.funding_source IS NULL
        """
    )

    # Backfill receipt_no: R{YYYYMMDD}{seq:04d} per session_date ordered by id
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   to_char(session_date, 'YYYYMMDD') AS d,
                   row_number() OVER (PARTITION BY session_date ORDER BY id) AS rn
            FROM session_records
        )
        UPDATE session_records sr
        SET receipt_no = 'R' || n.d || lpad(n.rn::text, 4, '0')
        FROM numbered n
        WHERE sr.id = n.id AND sr.receipt_no IS NULL
        """
    )

    op.create_unique_constraint(
        "uq_session_records_receipt_no", "session_records", ["receipt_no"]
    )

    # ── product_sales table ───────────────────────────────────────
    op.create_table(
        "product_sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payment_method", sa.String(20), nullable=True, server_default="cash"),
        sa.Column("payment_note", sa.String(200), nullable=True),
        sa.Column("receipt_no", sa.String(30), nullable=True, unique=True),
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("void_reason", sa.String(200), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("product_sales")
    op.drop_constraint("uq_session_records_receipt_no", "session_records", type_="unique")
    op.drop_column("session_records", "voided_by")
    op.drop_column("session_records", "voided_at")
    op.drop_column("session_records", "void_reason")
    op.drop_column("session_records", "is_void")
    op.drop_column("session_records", "discount_note")
    op.drop_column("session_records", "discount_amount")
    op.drop_column("session_records", "receipt_no")
    op.drop_column("session_records", "funding_source")
