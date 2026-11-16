"""既有機構預約補算 self_pay_amount（個案自付額）

zn4d 只回填了自費預約（自付額＝全額）；機構預約當時留成預設 0，其實是「未知」。
這支用與預約建立時相同的規則補算：

    自付額 = min(價目項目.self_pay_amount, 預約.amount)

價目項目只認預約自己存的 rate_item_id（建立當下選定的那一列）。算不出來（沒方案、
沒有價目項目、價目列已被刪）就設成 NULL，不猜。

只更新 appointments.self_pay_amount：不動 amount，不寫稽核或流水，不刪任何資料。
欄位改成可為 NULL（只是放寬限制；新預約仍由程式寫入 0 或算出的值，預設值不變）。

Revision ID: zq7a1b2c3d4e
Revises: zp6f0a1b2c3d
"""

import sqlalchemy as sa
from alembic import op

revision = "zq7a1b2c3d4e"
down_revision = "zp6f0a1b2c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("appointments", "self_pay_amount", existing_type=sa.Numeric(10, 2), nullable=True,
                    existing_server_default="0")
    bind = op.get_bind()
    # 價目項目存在才算得出來；LEAST 與 plan_pricing 的 min(self_pay, total) 相同
    bind.execute(sa.text("""
        UPDATE appointments a
           SET self_pay_amount = LEAST(COALESCE(r.self_pay_amount, 0), a.amount)
          FROM plan_rate_items r
         WHERE a.funding_source = 'institution'
           AND a.rate_item_id = r.id
           AND r.is_no_show_fee = false
    """))
    bind.execute(sa.text("""
        UPDATE appointments a
           SET self_pay_amount = NULL
         WHERE a.funding_source = 'institution'
           AND NOT EXISTS (
               SELECT 1 FROM plan_rate_items r
                WHERE r.id = a.rate_item_id AND r.is_no_show_fee = false)
    """))


def downgrade() -> None:
    # 資料不還原；只把 NULL 補回 0 再恢復 NOT NULL，不刪任何資料
    op.execute("UPDATE appointments SET self_pay_amount = 0 WHERE self_pay_amount IS NULL")
    op.alter_column("appointments", "self_pay_amount", existing_type=sa.Numeric(10, 2), nullable=False,
                    existing_server_default="0")
