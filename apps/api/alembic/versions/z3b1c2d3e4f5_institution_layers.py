"""Phase 1a: 機構三層（合約／方案／交通費）與額度三態

新增 institution_contracts、institution_plans、plan_transport_fees，
並為 case_institution_quotas 補上 plan_id 與額度三態欄位。

本 migration 為**純新增**：不改動、不刪除任何既有欄位，既有 API 與前端
不受影響。語意變更（amount 拆欄、status 加未到、收據改制等）排在 Phase 1b。
見 document_reference/gap_analysis.md §4 Phase 1。

Revision ID: z3b1c2d3e4f5
Revises: z2a1b2c3d4e5
"""

import sqlalchemy as sa
from alembic import op

revision = "z3b1c2d3e4f5"
down_revision = "z2a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institution_contracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("eligibility", sa.String(length=500), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("self_pay_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cap_type", sa.String(length=20), nullable=False, server_default="unlimited"),
        sa.Column("cap_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("contact_person", sa.String(length=100), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "cap_type IN ('amount','count','unlimited')",
            name="ck_institution_contracts_cap_type",
        ),
        sa.CheckConstraint(
            "(cap_type = 'unlimited') = (cap_value IS NULL)",
            name="ck_institution_contracts_cap_value",
        ),
    )
    op.create_index(
        "ix_institution_contracts_institution_id", "institution_contracts", ["institution_id"]
    )

    op.create_table(
        "institution_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("claim_unit", sa.String(length=200), nullable=True),
        sa.Column("claim_contact", sa.String(length=100), nullable=True),
        sa.Column("claim_phone", sa.String(length=50), nullable=True),
        sa.Column("per_person_count", sa.Integer(), nullable=True),
        sa.Column("annual_total_count", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["contract_id"], ["institution_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active','exhausted','expired')",
            name="ck_institution_plans_status",
        ),
    )
    op.create_index("ix_institution_plans_contract_id", "institution_plans", ["contract_id"])

    op.create_table(
        "plan_transport_fees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["plan_id"], ["institution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_transport_fees_plan_id", "plan_transport_fees", ["plan_id"])

    # --- 額度三態 ---------------------------------------------------------
    op.add_column("case_institution_quotas", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.add_column(
        "case_institution_quotas",
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "case_institution_quotas",
        sa.Column("reserved_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "case_institution_quotas",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.create_foreign_key(
        "fk_case_quotas_plan", "case_institution_quotas", "institution_plans",
        ["plan_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_case_institution_quotas_plan_id", "case_institution_quotas", ["plan_id"])

    # 既有資料回填：尚未使用的額度一律視為「已預留」，維持恆等式
    #   used + booked + reserved = total_count
    op.execute(
        "UPDATE case_institution_quotas "
        "SET reserved_count = GREATEST(total_count - used_count, 0)"
    )
    op.create_check_constraint(
        "ck_case_quotas_tristate",
        "case_institution_quotas",
        "used_count + booked_count + reserved_count = total_count",
    )


def downgrade() -> None:
    op.drop_constraint("ck_case_quotas_tristate", "case_institution_quotas", type_="check")
    op.drop_index("ix_case_institution_quotas_plan_id", table_name="case_institution_quotas")
    op.drop_constraint("fk_case_quotas_plan", "case_institution_quotas", type_="foreignkey")
    op.drop_column("case_institution_quotas", "status")
    op.drop_column("case_institution_quotas", "reserved_count")
    op.drop_column("case_institution_quotas", "booked_count")
    op.drop_column("case_institution_quotas", "plan_id")

    op.drop_index("ix_plan_transport_fees_plan_id", table_name="plan_transport_fees")
    op.drop_table("plan_transport_fees")
    op.drop_index("ix_institution_plans_contract_id", table_name="institution_plans")
    op.drop_table("institution_plans")
    op.drop_index("ix_institution_contracts_institution_id", table_name="institution_contracts")
    op.drop_table("institution_contracts")
