"""既有機構預約的 self_pay_amount：優先採用 session_records 的實際自付額

順序：
1. 有對應的有效 session_records（appointment_id 相同、is_void=false）：
   - 自付額 > 0，或機構請款額 > 0 → 採用該筆 self_pay_amount（機構請款額 > 0 且自付 0＝全額補助，存 0）。
   - 兩者皆 0（沒有可靠資訊）→ 不採用，往下一步。
2. 還是 NULL 且有價目項目：min(價目自付額, 預約總額)（與 zq7a 相同規則）。
3. 都沒有 → 維持 NULL（畫面顯示「未設定」，不猜）。

只更新 appointments.self_pay_amount：不動 amount，不寫稽核或流水，不刪任何資料。

Revision ID: zt0d4e5f6a7b
Revises: zs9c3d4e5f6a
"""

import sqlalchemy as sa
from alembic import op

revision = "zt0d4e5f6a7b"
down_revision = "zs9c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE appointments a
           SET self_pay_amount = LEAST(s.self_pay_amount, a.amount)
          FROM session_records s
         WHERE s.appointment_id = a.id
           AND s.is_void = false
           AND a.funding_source = 'institution'
           AND (s.self_pay_amount > 0 OR s.institution_claim_amount > 0)
    """))
    bind.execute(sa.text("""
        UPDATE appointments a
           SET self_pay_amount = LEAST(COALESCE(r.self_pay_amount, 0), a.amount)
          FROM plan_rate_items r
         WHERE a.funding_source = 'institution'
           AND a.self_pay_amount IS NULL
           AND a.rate_item_id = r.id
           AND r.is_no_show_fee = false
    """))


def downgrade() -> None:
    # 資料不還原（不刪任何資料）
    pass
