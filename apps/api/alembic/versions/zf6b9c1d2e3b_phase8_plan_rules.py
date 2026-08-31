"""Phase 8: 機構方案進階規則

依《系統架構規劃與機構合約清冊 對照確認事項》重建機構方案的資料模型。
Phase 1a 的「一個方案一個鐘點費」裝不下清冊裡的實際樣態，本次撐開。

七項落差對應：
  問題2 多元價目      → plan_rate_items（依服務型態／時長／第幾次不同單價）
  問題1 累積門檻      → institution_plans.claim_threshold_sessions
  問題3 核銷登記時數  → plan_rate_items.claim_hours / claim_unit_rate
                        ＋ session_records.claim_hours / claim_unit_rate
  問題4 回扣型方案    → institution_contracts.settlement_direction / rebate_rate
  問題5 額度單位      → institution_plans.quota_unit（count｜amount）、
                        per_person_monthly_limit、extension_sessions
  問題6 收據品項      → plan_rate_items 的自付／機構兩側收費名目
  問題7 價格來源      → institution_plans.pricing_mode

Revision ID: zf6b9c1d2e3b
Revises: ze5a8b9c1d2a
"""

import sqlalchemy as sa
from alembic import op

revision = "zf6b9c1d2e3b"
down_revision = "ze5a8b9c1d2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 問題4：回扣型方案 —— 機構直接匯給心理師，慈恩對機構沒有應收 ──
    op.add_column(
        "institution_contracts",
        sa.Column(
            "settlement_direction", sa.String(length=20),
            nullable=False, server_default="to_clinic",
        ),
    )
    # 回扣比例：心理師收到機構款項後回繳給慈恩的比例（0–1）
    op.add_column("institution_contracts", sa.Column("rebate_rate", sa.Numeric(5, 4), nullable=True))
    # 回繳方式：transfer 心理師自行匯款／payout_deduct 從當月酬勞扣除
    op.add_column("institution_contracts", sa.Column("rebate_method", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_contracts_settlement_direction", "institution_contracts",
        "settlement_direction IN ('to_clinic','to_therapist')",
    )
    op.create_check_constraint(
        "ck_contracts_rebate_method", "institution_contracts",
        "rebate_method IS NULL OR rebate_method IN ('transfer','payout_deduct')",
    )
    # 回扣型必須有回繳比例，否則帳會算不出來
    op.create_check_constraint(
        "ck_contracts_rebate_required", "institution_contracts",
        "settlement_direction = 'to_clinic' OR rebate_rate IS NOT NULL",
    )

    # ── 問題1／5／7：方案層規則 ──
    op.add_column(
        "institution_plans",
        sa.Column("claim_threshold_sessions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_plans",
        sa.Column("quota_unit", sa.String(length=10), nullable=False, server_default="count"),
    )
    # quota_unit='amount' 時使用（如國軍 $149,000）
    op.add_column("institution_plans", sa.Column("annual_total_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("institution_plans", sa.Column("per_person_amount", sa.Numeric(12, 2), nullable=True))
    # 容愛協會：每月最多 4 次、全部累計最多 24 次
    op.add_column("institution_plans", sa.Column("per_person_monthly_limit", sa.Integer(), nullable=True))
    # 警局、奇美家照：基本 6 次，經評估後可再延長 3 次
    op.add_column("institution_plans", sa.Column("extension_sessions", sa.Integer(), nullable=True))
    # contract_fixed 合約談定固定價／therapist_rate 依心理師鐘點費
    op.add_column(
        "institution_plans",
        sa.Column("pricing_mode", sa.String(length=20), nullable=False, server_default="contract_fixed"),
    )
    op.create_check_constraint(
        "ck_plans_quota_unit", "institution_plans", "quota_unit IN ('count','amount')"
    )
    op.create_check_constraint(
        "ck_plans_pricing_mode", "institution_plans",
        "pricing_mode IN ('contract_fixed','therapist_rate')",
    )
    op.create_check_constraint(
        "ck_plans_amount_quota", "institution_plans",
        "quota_unit = 'count' OR annual_total_amount IS NOT NULL OR per_person_amount IS NOT NULL",
    )

    # ── 問題2／3／6：方案價目表 ──
    op.create_table(
        "plan_rate_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),  # 個別諮商／家族諮商／講座／團輔
        # 對應諮商型態；NULL＝不限（由行政挑選）
        sa.Column("service_type", sa.String(length=30), nullable=True),
        # 時長：緯穎 50 分／100 分、國軍團輔 1.5hr
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        # 第幾次適用（衛生局市民第1次免費、蛹之生第3次起）；NULL＝不限
        sa.Column("session_seq_from", sa.Integer(), nullable=True),
        sa.Column("session_seq_to", sa.Integer(), nullable=True),
        # 金額拆兩側
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("self_pay_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        # 問題6：兩側的收據品項可以不同
        sa.Column("self_pay_receipt_item", sa.String(length=100), nullable=True),
        sa.Column("institution_receipt_item", sa.String(length=100), nullable=True),
        # 問題3：核銷單上登記的時數與單價（與實際諮商時數不同時填寫）
        sa.Column("claim_hours", sa.Numeric(5, 2), nullable=True),
        sa.Column("claim_unit_rate", sa.Numeric(10, 2), nullable=True),
        # 南家扶：無事先請假爽約費 $200
        sa.Column("is_no_show_fee", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["plan_id"], ["institution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("self_pay_amount <= total_amount", name="ck_rate_item_self_pay"),
        sa.CheckConstraint(
            "session_seq_from IS NULL OR session_seq_to IS NULL "
            "OR session_seq_to >= session_seq_from",
            name="ck_rate_item_seq_order",
        ),
        # 核銷時數與單價要嘛都填、要嘛都不填
        sa.CheckConstraint(
            "(claim_hours IS NULL) = (claim_unit_rate IS NULL)",
            name="ck_rate_item_claim_pair",
        ),
    )
    op.create_index("ix_plan_rate_items_plan", "plan_rate_items", ["plan_id"])

    # ── 問題3：紀錄層留存核銷登記時數（與實際時數分開存）──
    op.add_column("session_records", sa.Column("rate_item_id", sa.Integer(), nullable=True))
    op.add_column("session_records", sa.Column("claim_hours", sa.Numeric(5, 2), nullable=True))
    op.add_column("session_records", sa.Column("claim_unit_rate", sa.Numeric(10, 2), nullable=True))
    op.create_foreign_key(
        "fk_session_records_rate_item", "session_records", "plan_rate_items",
        ["rate_item_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("appointments", sa.Column("rate_item_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_rate_item", "appointments", "plan_rate_items",
        ["rate_item_id"], ["id"], ondelete="SET NULL",
    )

    # ── 問題5：個案額度的延長核准紀錄 ──
    op.add_column(
        "case_institution_quotas",
        sa.Column("extension_granted", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("case_institution_quotas", sa.Column("extension_note", sa.String(length=500), nullable=True))
    op.add_column("case_institution_quotas", sa.Column("extension_by", sa.Integer(), nullable=True))
    op.add_column("case_institution_quotas", sa.Column("extension_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_case_quotas_extension_by", "case_institution_quotas", "users",
        ["extension_by"], ["id"], ondelete="SET NULL",
    )

    # 既有合約的單一鐘點費搬進價目表，成為該方案的預設項目
    op.execute(
        """
        INSERT INTO plan_rate_items
            (plan_id, label, total_amount, self_pay_amount, sort_order)
        SELECT p.id, '預設', c.hourly_rate, c.self_pay_amount, 0
        FROM institution_plans p
        JOIN institution_contracts c ON c.id = p.contract_id
        WHERE NOT EXISTS (SELECT 1 FROM plan_rate_items r WHERE r.plan_id = p.id)
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_case_quotas_extension_by", "case_institution_quotas", type_="foreignkey")
    for c in ("extension_at", "extension_by", "extension_note", "extension_granted"):
        op.drop_column("case_institution_quotas", c)

    op.drop_constraint("fk_appointments_rate_item", "appointments", type_="foreignkey")
    op.drop_column("appointments", "rate_item_id")
    op.drop_constraint("fk_session_records_rate_item", "session_records", type_="foreignkey")
    for c in ("claim_unit_rate", "claim_hours", "rate_item_id"):
        op.drop_column("session_records", c)

    op.drop_index("ix_plan_rate_items_plan", table_name="plan_rate_items")
    op.drop_table("plan_rate_items")

    for name in ("ck_plans_amount_quota", "ck_plans_pricing_mode", "ck_plans_quota_unit"):
        op.drop_constraint(name, "institution_plans", type_="check")
    for c in ("pricing_mode", "extension_sessions", "per_person_monthly_limit",
              "per_person_amount", "annual_total_amount", "quota_unit",
              "claim_threshold_sessions"):
        op.drop_column("institution_plans", c)

    for name in ("ck_contracts_rebate_required", "ck_contracts_rebate_method",
                 "ck_contracts_settlement_direction"):
        op.drop_constraint(name, "institution_contracts", type_="check")
    for c in ("rebate_method", "rebate_rate", "settlement_direction"):
        op.drop_column("institution_contracts", c)
