"""機構合約子系統：合約/方案/費率/額度池/個案機構狀態/核銷案容器七張表，
以及主系統 appointments / session_records 上的報價快照欄位。

見 V2升級計畫 07_機構合約子系統架構.html。這是文件裡「主系統只增 6 欄，
其餘全部收斂進子系統」的落地版本——本次先讓骨架跑得動，54 個方案的完整
資料靠 institution/seed_plans.py 陸續補齊，不在這支 migration 裡塞資料。

建表順序（配合 FK 相依）：
    inst_quota_pools（無 FK 到其他子系統表，先建）
    inst_contracts（FK -> institutions）
    inst_plans（FK -> inst_contracts, inst_quota_pools）
    inst_rate_rules（FK -> inst_plans）
    inst_enrollments（FK -> cases, inst_plans）
    inst_claim_cases（無 FK 到其他子系統表）
    inst_claim_lines（FK -> inst_claim_cases, session_records）

appointments / session_records 各加 6 個報價快照欄位（plan_id 除外，
session_records 沒有獨立的 plan FK 名稱衝突問題，兩邊命名一致）。

Revision ID: aa2a2b3c4d5f2
Revises: aa1a2b3c4d5f1
Create Date: 2026-09-07 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "aa2a2b3c4d5f2"
down_revision = "aa1a2b3c4d5f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── inst_quota_pools ────────────────────────────────────────────────
    op.create_table(
        "inst_quota_pools",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contract_id", sa.Integer, nullable=False),  # FK 補在 inst_contracts 建完後
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False, server_default="count"),
        sa.Column("total_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("consumed_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
    )

    # ── inst_contracts ──────────────────────────────────────────────────
    op.create_table(
        "inst_contracts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("institution_id", sa.Integer, sa.ForeignKey("institutions.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("contact_note", sa.Text, nullable=True),
        sa.Column("eligibility_note", sa.Text, nullable=True),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "fk_quota_pool_contract", "inst_quota_pools", "inst_contracts", ["contract_id"], ["id"]
    )

    # ── inst_plans ──────────────────────────────────────────────────────
    op.create_table(
        "inst_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contract_id", sa.Integer, sa.ForeignKey("inst_contracts.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quota_pool_id", sa.Integer, sa.ForeignKey("inst_quota_pools.id"), nullable=True, index=True),
        sa.Column("quota_unit", sa.String(10), nullable=False, server_default="count"),
        sa.Column("default_quota_limit", sa.String(30), nullable=True),
        sa.Column("default_quota_limit_numeric", sa.Integer, nullable=True),
        sa.Column("period_limit", sa.Integer, nullable=True),
        sa.Column("period_unit", sa.String(10), nullable=True),
        sa.Column("requires_assessment", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("counts_toward_quota", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("requires_external_code", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("compensation_mode", sa.String(12), nullable=False, server_default="commission"),
        sa.Column("case_receipt_required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("case_receipt_item_name", sa.String(50), nullable=True),
        sa.Column("institution_receipt_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("institution_receipt_item_name", sa.String(50), nullable=True),
        sa.Column("claim_group_key", sa.String(100), nullable=True, index=True),
        sa.Column("claim_timing", sa.String(12), nullable=False, server_default="monthly"),
        sa.Column("claim_deadline_day", sa.Integer, nullable=True),
        sa.Column("claim_grouping_mode", sa.String(20), nullable=False, server_default="period"),
        sa.Column("claim_capacity", sa.Integer, nullable=True),
        sa.Column("registered_hours_rule", sa.String(200), nullable=True),
        sa.Column("admin_checklist", sa.Text, nullable=True),
        sa.Column("therapist_checklist", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── inst_rate_rules ─────────────────────────────────────────────────
    op.create_table(
        "inst_rate_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("inst_plans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("when_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("price_source", sa.String(20), nullable=False, server_default="fixed"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("case_payable", sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.Column("label", sa.String(100), nullable=True),
    )

    # ── inst_enrollments ────────────────────────────────────────────────
    op.create_table(
        "inst_enrollments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("inst_plans.id"), nullable=False, index=True),
        sa.Column("external_case_code", sa.String(50), nullable=True),
        sa.Column("quota_unit", sa.String(10), nullable=False, server_default="count"),
        sa.Column("quota_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("reserved_count", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("used_count", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("extended_count", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("extension_approved_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("extension_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extension_note", sa.Text, nullable=True),
        sa.Column("period_limit", sa.Integer, nullable=True),
        sa.Column("period_unit", sa.String(10), nullable=True),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
        sa.Column("assessment_status", sa.String(20), nullable=False, server_default="not_required"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "plan_id", name="uq_enrollment_case_plan"),
    )

    # ── inst_claim_cases ────────────────────────────────────────────────
    op.create_table(
        "inst_claim_cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("claim_no", sa.String(20), nullable=False, unique=True),
        sa.Column("claim_group_key", sa.String(100), nullable=False, index=True),
        sa.Column("grouping_mode", sa.String(20), nullable=False, server_default="period"),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="collecting"),
        sa.Column("settlement_mode", sa.String(20), nullable=False, server_default="claim_then_pay"),
        sa.Column("applied_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("received_date", sa.Date, nullable=True),
        sa.Column("received_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("income_tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("transfer_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("net_received", sa.Numeric(12, 2), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_reason", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── inst_claim_lines ────────────────────────────────────────────────
    op.create_table(
        "inst_claim_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "claim_case_id", sa.Integer, sa.ForeignKey("inst_claim_cases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("session_record_id", sa.Integer, sa.ForeignKey("session_records.id"), nullable=False, index=True),
        sa.Column("claimed_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("actual_hours", sa.Numeric(4, 2), nullable=True),
        sa.Column("registered_hours", sa.Numeric(4, 2), nullable=True),
        sa.Column("registered_unit_price", sa.Numeric(10, 2), nullable=True),
        sa.UniqueConstraint("session_record_id", name="uq_claim_line_session_record"),
    )

    # ── 主系統：appointments / session_records 報價快照欄位（07 §4.2、§7.1）──
    for table in ("appointments", "session_records"):
        op.add_column(table, sa.Column("plan_id", sa.Integer, sa.ForeignKey("inst_plans.id"), nullable=True))
        op.add_column(table, sa.Column("case_payable", sa.Numeric(10, 2), nullable=True))
        op.add_column(table, sa.Column("institution_payable", sa.Numeric(10, 2), nullable=True))
        op.add_column(table, sa.Column("compensation_mode", sa.String(12), nullable=True))
        op.add_column(table, sa.Column("commissionable_base", sa.Numeric(10, 2), nullable=True))
        op.add_column(table, sa.Column("plan_quote", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    for table in ("session_records", "appointments"):
        op.drop_column(table, "plan_quote")
        op.drop_column(table, "commissionable_base")
        op.drop_column(table, "compensation_mode")
        op.drop_column(table, "institution_payable")
        op.drop_column(table, "case_payable")
        op.drop_column(table, "plan_id")

    op.drop_table("inst_claim_lines")
    op.drop_table("inst_claim_cases")
    op.drop_table("inst_enrollments")
    op.drop_table("inst_rate_rules")
    op.drop_table("inst_plans")
    op.drop_constraint("fk_quota_pool_contract", "inst_quota_pools", type_="foreignkey")
    op.drop_table("inst_contracts")
    op.drop_table("inst_quota_pools")
