"""P1 出席驅動·報到三步驟後兩步：收款、開立收據

見 V2升級計畫 01 §A2、02 §1.2、08_實作進度與系統架構現況.html §8 下一步第1項。

- fee_items：收費項目主檔（收據品項下拉來源），seed 8 個定稿預設值。
- receipts：報到當場開立收據的持久化紀錄。
- session_records +copay_collected_at/copay_payment_method/copay_payment_note：
  櫃檯今天有沒有收到個案自付額，與既有 payment_status（機構請款進度）刻意
  分開，避免撞語意（見 models/session_record.py 同一段的說明）。

Revision ID: aa4a2b3c4d5f4
Revises: aa3a2b3c4d5f3
Create Date: 2026-09-07 00:00:00.000003
"""
from alembic import op
import sqlalchemy as sa

revision = "aa4a2b3c4d5f4"
down_revision = "aa3a2b3c4d5f3"
branch_labels = None
depends_on = None

DEFAULT_FEE_ITEMS = [
    ("諮商", False), ("會談", False), ("專業評估", False), ("心理治療", True),
    ("人際互動治療", False), ("摘要報告", False), ("會面交往", False), ("工作坊", False),
]


def upgrade() -> None:
    op.create_table(
        "fee_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("receipt_no", sa.String(30), nullable=False, unique=True),
        sa.Column("session_record_id", sa.Integer, sa.ForeignKey("session_records.id"), nullable=True, index=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("fee_item_id", sa.Integer, sa.ForeignKey("fee_items.id"), nullable=True),
        sa.Column("fee_item_custom_name", sa.String(100), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="issued"),
        sa.Column("void_reason", sa.String(200), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("session_records", sa.Column("copay_collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("session_records", sa.Column("copay_payment_method", sa.String(20), nullable=True))
    op.add_column("session_records", sa.Column("copay_payment_note", sa.String(200), nullable=True))

    fee_items_table = sa.table(
        "fee_items",
        sa.column("name", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        fee_items_table,
        [
            {"name": name, "is_default": is_default, "is_active": True, "sort_order": i}
            for i, (name, is_default) in enumerate(DEFAULT_FEE_ITEMS)
        ],
    )


def downgrade() -> None:
    op.drop_column("session_records", "copay_payment_note")
    op.drop_column("session_records", "copay_payment_method")
    op.drop_column("session_records", "copay_collected_at")
    op.drop_table("receipts")
    op.drop_table("fee_items")
