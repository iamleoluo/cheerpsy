"""諮商型態維度：appointments / session_records 加 consult_type + location_kind

07 §6.2 的費率規則有「諮商型態」這個計價維度（個別/伴侶/家族/親職/團體/
講座/會議），但程式碼裡從來沒有這個欄位——seed_plans.py 只好把它寫成
`{"session_type": "individual"}`，而執行期的 session_type 是 in_person/
online/outdoor，永遠比不中，那些方案一律報價 $0。

這不是打字錯誤，是真的少一個維度：家防中心的 個別$2000 / 親職$1000 /
家族$2400 三者都是「現場」進行，塞不進 session_type。

location_kind 同理：QuoteRequest 早就有這個欄位，但 create_appointment
硬寫 "clinic"，所以 `{"location_kind": "home"}` 這類規則也是死的。

Revision ID: ad0d5e6f7b02
Revises: ac9c4d5e6a01
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "ad0d5e6f7b02"
down_revision = "ac9c4d5e6a01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("consult_type", sa.String(20), nullable=False, server_default="individual"))
    op.add_column("appointments", sa.Column("location_kind", sa.String(20), nullable=False, server_default="clinic"))
    op.add_column("session_records", sa.Column("consult_type", sa.String(20), nullable=True))
    op.add_column("session_records", sa.Column("location_kind", sa.String(20), nullable=True))
    # 既有 session_records 從對應的 appointment 補上快照（沒有 appointment 的
    # 拆帳子紀錄就留 NULL）
    op.execute(
        "UPDATE session_records sr SET consult_type = a.consult_type, location_kind = a.location_kind "
        "FROM appointments a WHERE sr.appointment_id = a.id"
    )


def downgrade() -> None:
    op.drop_column("session_records", "location_kind")
    op.drop_column("session_records", "consult_type")
    op.drop_column("appointments", "location_kind")
    op.drop_column("appointments", "consult_type")
