"""P1 出席驅動：appointments 加報到狀態機欄位

見 V2升級計畫 01 §A1、02 §4.1、08_實作進度與系統架構現況.html §8 下一步第1項。

check_in_status 三態（pending/arrived/no_show）取代「時間到就自動結算」——
appointments/{id}/check-in 端點是新的主要觸發路徑，
services/settlement.py 的 materialize_due_appointments() 降級為只處理
仍是 pending 的漏網之魚（補登安全網）。

Revision ID: aa3a2b3c4d5f3
Revises: aa2a2b3c4d5f2
Create Date: 2026-09-07 00:00:00.000002
"""
from alembic import op
import sqlalchemy as sa

revision = "aa3a2b3c4d5f3"
down_revision = "aa2a2b3c4d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("check_in_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("appointments", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("checked_in_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("appointments", sa.Column("no_show_reason", sa.String(20), nullable=True))
    op.add_column("appointments", sa.Column("no_show_note", sa.String(200), nullable=True))
    op.add_column("appointments", sa.Column("no_show_followup", sa.String(20), nullable=True))

    # 既有資料回填：status='executed' 的舊紀錄視為「已到」，避免它們被新的
    # check_in_status='pending' 過濾邏輯誤判成漏網之魚、被 materialize 重新處理。
    op.execute("UPDATE appointments SET check_in_status = 'arrived' WHERE status = 'executed'")


def downgrade() -> None:
    op.drop_column("appointments", "no_show_followup")
    op.drop_column("appointments", "no_show_note")
    op.drop_column("appointments", "no_show_reason")
    op.drop_column("appointments", "checked_in_by")
    op.drop_column("appointments", "checked_in_at")
    op.drop_column("appointments", "check_in_status")
