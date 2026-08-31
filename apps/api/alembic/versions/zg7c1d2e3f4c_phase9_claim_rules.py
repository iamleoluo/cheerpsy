"""Phase 9: 依慈恩回覆調整核銷、收款與計價規則

來源：《系統架構與機構合約清冊 對照確認事項 — 慈恩回覆》。
七題全部有答案，其中數處推翻 Phase 8 的假設。

Revision ID: zg7c1d2e3f4c
Revises: zf6b9c1d2e3b
"""

import sqlalchemy as sa
from alembic import op

revision = "zg7c1d2e3f4c"
down_revision = "zf6b9c1d2e3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Q25：核銷案 ────────────────────────────────────────────────
    # 核銷模式。period_start/end 自此**不再綁定**，只作為撈紀錄的參考區間；
    # 最終區間在送出核銷時才確定（慈恩：「不要綁定核銷案的時間區間，
    # 送出核銷案時才會是最終的時間區間」「時間的區間是為了撈紀錄，沒有要綁定」）。
    #   monthly    月核銷 → 以前一個月份的紀錄
    #   quarterly  季核銷 → 以前三個月份的紀錄
    #   semester   學期核銷 → 以上/下學期計算
    #   threshold  次數達標 → 個案諮商次數達規定時，以達標那個月份送出
    op.add_column(
        "claim_batches",
        sa.Column("claim_mode", sa.String(length=20), nullable=False, server_default="monthly"),
    )
    # 撥款模式（慈恩：核銷方案有三種）
    #   claim_first        先核銷，後撥款
    #   prepay_then_claim  先撥款，後核銷（類似儲值）
    #   prepay_no_claim    先撥款，不核銷，後補收據
    op.add_column(
        "claim_batches",
        sa.Column("funding_mode", sa.String(length=20), nullable=False, server_default="claim_first"),
    )
    # 送出核銷時定案的實際區間（與 period_start/end 的「參考區間」分開）
    op.add_column("claim_batches", sa.Column("final_period_start", sa.Date(), nullable=True))
    op.add_column("claim_batches", sa.Column("final_period_end", sa.Date(), nullable=True))

    # 收款明細（慈恩提供的機構清冊畫面欄位）
    op.add_column("claim_batches", sa.Column("applied_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("claim_batches", sa.Column("received_date", sa.Date(), nullable=True))
    op.add_column("claim_batches", sa.Column("received_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "claim_batches",
        sa.Column("tax_withheld", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("claim_batches", sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("claim_batches", sa.Column("transfer_fee", sa.Numeric(10, 2), nullable=True))
    op.add_column("claim_batches", sa.Column("net_amount", sa.Numeric(12, 2), nullable=True))
    # 收款後鎖定；要改需向上一層權限
    op.add_column(
        "claim_batches",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("claim_batches", sa.Column("unlocked_by", sa.Integer(), nullable=True))
    op.add_column("claim_batches", sa.Column("unlock_reason", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_claim_batches_unlocked_by", "claim_batches", "users",
        ["unlocked_by"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_claim_batches_claim_mode", "claim_batches",
        "claim_mode IN ('monthly','quarterly','semester','threshold')",
    )
    op.create_check_constraint(
        "ck_claim_batches_funding_mode", "claim_batches",
        "funding_mode IN ('claim_first','prepay_then_claim','prepay_no_claim')",
    )

    # 機構核銷收入依「該筆諮商紀錄的月份」認列為當月應收
    # （慈恩：「機構核銷的收入，是依該筆諮商紀錄的月份，為當月應收金額」）
    # session_records.session_date 已足以推導，不另存欄位。

    # ── Q30：機構收據 ──────────────────────────────────────────────
    # 衛生局市民／15-45青壯／國軍 都不用開機構收據，只有台南教支需要
    op.add_column(
        "institution_contracts",
        sa.Column("requires_institution_receipt", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── Q28：回扣改為由抽成推導 ────────────────────────────────────
    # 慈恩：「依方案的鐘點費＋心理師個別的抽成，去計算回扣的金額」
    #       「回繳方式：當月酬勞扣除」
    # 因此 rebate_rate 不再手填，改由 (1 − 心理師抽成率) 推導；
    # 欄位保留為「覆寫值」，NULL 代表依抽成計算。
    op.alter_column(
        "institution_contracts", "rebate_rate",
        existing_type=sa.Numeric(5, 4), nullable=True,
        comment="回繳比例覆寫值；NULL = 依 (1 − 心理師抽成率) 計算",
    )
    # 回繳方式固定為當月酬勞扣除，既有資料一併校正
    op.execute(
        "UPDATE institution_contracts SET rebate_method = 'payout_deduct' "
        "WHERE settlement_direction = 'to_therapist'"
    )
    # 原本要求回扣型必須填 rebate_rate 的約束改為不需要（可由抽成推導）
    op.drop_constraint("ck_contracts_rebate_required", "institution_contracts", type_="check")

    # 回扣金額記在帳冊紀錄上，月報表據此從心理師酬勞扣除
    op.add_column("session_records", sa.Column("rebate_amount", sa.Numeric(10, 2), nullable=True))

    # ── Q31：價格來源多一種 ────────────────────────────────────────
    # therapist_defined：心理師自己設定金額（聊心茶室、遠距抱抱）
    op.drop_constraint("ck_plans_pricing_mode", "institution_plans", type_="check")
    op.create_check_constraint(
        "ck_plans_pricing_mode", "institution_plans",
        "pricing_mode IN ('contract_fixed','therapist_rate','therapist_defined')",
    )

    # ── Q27：核銷登記時數改在建立核銷案時才轉出 ────────────────────
    # session_records 的 claim_hours / claim_unit_rate 保留，但改為
    # 「加入核銷案時才寫入」，預約與報到階段不填。
    op.add_column(
        "session_records",
        sa.Column("claim_registered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_records", "claim_registered_at")
    op.drop_constraint("ck_plans_pricing_mode", "institution_plans", type_="check")
    op.create_check_constraint(
        "ck_plans_pricing_mode", "institution_plans",
        "pricing_mode IN ('contract_fixed','therapist_rate')",
    )
    op.drop_column("session_records", "rebate_amount")
    op.create_check_constraint(
        "ck_contracts_rebate_required", "institution_contracts",
        "settlement_direction = 'to_clinic' OR rebate_rate IS NOT NULL",
    )
    op.drop_column("institution_contracts", "requires_institution_receipt")

    op.drop_constraint("ck_claim_batches_funding_mode", "claim_batches", type_="check")
    op.drop_constraint("ck_claim_batches_claim_mode", "claim_batches", type_="check")
    op.drop_constraint("fk_claim_batches_unlocked_by", "claim_batches", type_="foreignkey")
    for c in ("unlock_reason", "unlocked_by", "is_locked", "net_amount", "transfer_fee",
              "tax_amount", "tax_withheld", "received_amount", "received_date",
              "applied_amount", "final_period_end", "final_period_start",
              "funding_mode", "claim_mode"):
        op.drop_column("claim_batches", c)
