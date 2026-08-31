"""Phase 5: 機構核銷案

依 open_questions Q1–Q4：
  Q1 子列表可逐筆增減紀錄（既有 router 已支援）
  Q2 每月 1 號起可建案、滾動加入紀錄；期間為參考區間，不硬檢查缺口／重疊
  Q3 一個核銷案可跨方案 → claim_batches ↔ plans 改 1:N
  Q4 鐘點費可回溯修改，寫 audit_log，不重算酬勞（Q22）

Revision ID: z8a2b3c4d5ea
Revises: z7f1a2b3c4d9
"""

import sqlalchemy as sa
from alembic import op

revision = "z8a2b3c4d5ea"
down_revision = "z7f1a2b3c4d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Q3：一案可跨方案。institution_id 保留（同一機構），方案改走連結表。
    op.create_table(
        "claim_batch_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_batch_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["claim_batch_id"], ["claim_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["institution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_batch_id", "plan_id", name="uq_claim_batch_plan"),
    )
    op.create_index("ix_claim_batch_plans_batch", "claim_batch_plans", ["claim_batch_id"])

    # 心理師依核銷案上傳的附件三類（心智圖 §三.3）
    op.create_table(
        "claim_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_batch_id", sa.Integer(), nullable=False),
        sa.Column("therapist_id", sa.Integer(), nullable=False),
        # receipt 領據／monthly_list 月次清冊表／other 其他
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=300), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["claim_batch_id"], ["claim_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["therapist_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "doc_type IN ('receipt','monthly_list','other')", name="ck_claim_document_type"
        ),
    )
    op.create_index("ix_claim_documents_batch", "claim_documents", ["claim_batch_id"])

    # 退回補件：清除心理師確認與行政核對，回「待提交」並記錄原因
    op.add_column("session_records", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("session_records", sa.Column("rejected_reason", sa.String(length=500), nullable=True))
    op.add_column("session_records", sa.Column("rejected_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_session_records_rejected_by", "session_records", "users",
        ["rejected_by"], ["id"], ondelete="SET NULL",
    )

    # 既有的單一 institution_id 方案關聯，若 claim_batches 有 plan 概念則遷移；
    # 目前 claim_batches 只有 institution_id，無 plan_id，故無資料需搬。


def downgrade() -> None:
    op.drop_constraint("fk_session_records_rejected_by", "session_records", type_="foreignkey")
    op.drop_column("session_records", "rejected_by")
    op.drop_column("session_records", "rejected_reason")
    op.drop_column("session_records", "rejected_at")
    op.drop_index("ix_claim_documents_batch", table_name="claim_documents")
    op.drop_table("claim_documents")
    op.drop_index("ix_claim_batch_plans_batch", table_name="claim_batch_plans")
    op.drop_table("claim_batch_plans")
