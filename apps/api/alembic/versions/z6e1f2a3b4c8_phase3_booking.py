"""Phase 3: 預約作業與診間主控台

appointments 補齊諮商項目、方案、交通費、視訊連結、外展地點、報到狀態
與當次金額（D1）；rooms 加類型並補齊 12 間；新增 holidays。

額度三態的**流轉**在本階段接上（Phase 1a 只建了欄位）：
  排預約 → 已預留轉已預約
  報到已到 → 已預約轉已使用
  未到／取消 → 已預約退回已預留

Revision ID: z6e1f2a3b4c8
Revises: z5d1e2f3a4b7
"""

import sqlalchemy as sa
from alembic import op

revision = "z6e1f2a3b4c8"
down_revision = "z5d1e2f3a4b7"
branch_labels = None
depends_on = None

# 12 間診間，僅 2C、2E 為兒童遊戲室（原型 rooms 定案①）
ROOMS = [
    ("2A", 2, "talk"), ("2B", 2, "talk"), ("2C", 2, "play"),
    ("2D", 2, "talk"), ("2E", 2, "play"), ("2F", 2, "talk"),
    ("3A", 3, "talk"), ("3B", 3, "talk"), ("3C", 3, "talk"),
    ("3D", 3, "talk"), ("3E", 3, "talk"), ("3F", 3, "talk"),
]


def upgrade() -> None:
    # --- appointments ------------------------------------------------------
    op.add_column("appointments", sa.Column("fee_item", sa.String(length=30), nullable=True))
    op.add_column("appointments", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("transport_fee", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("appointments", sa.Column("transport_fee_option_id", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("video_link", sa.String(length=500), nullable=True))
    op.add_column("appointments", sa.Column("notify_admin_to_forward", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("appointments", sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("outreach_location", sa.String(length=300), nullable=True))
    # 報到狀態：pending 待報到／arrived 已到／absent 未到
    op.add_column("appointments", sa.Column("checkin_status", sa.String(length=20), nullable=False, server_default="pending"))
    op.add_column("appointments", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("checked_in_by", sa.Integer(), nullable=True))
    # D1：當次金額。心理師每次預約可填，預設帶該個案上次金額 → users.base_price
    op.add_column("appointments", sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=True))
    # 媒合初診標記，診間日曆用黃框呈現
    op.add_column("appointments", sa.Column("is_intake", sa.Boolean(), nullable=False, server_default="false"))

    op.create_foreign_key("fk_appointments_plan", "appointments", "institution_plans",
                          ["plan_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_appointments_transport_fee", "appointments", "plan_transport_fees",
                          ["transport_fee_option_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_appointments_checked_in_by", "appointments", "users",
                          ["checked_in_by"], ["id"], ondelete="SET NULL")
    op.create_check_constraint(
        "ck_appointments_checkin_status", "appointments",
        "checkin_status IN ('pending','arrived','absent')",
    )
    # 使用診間則無交通費（心智圖 §二）
    op.create_check_constraint(
        "ck_appointments_transport_fee", "appointments",
        "room_id IS NULL OR transport_fee = 0",
    )
    # 既有已執行的紀錄視為已報到，避免主控台把歷史資料顯示成待報到
    op.execute("UPDATE appointments SET checkin_status = 'arrived' WHERE status = 'executed'")
    op.execute("UPDATE appointments SET checkin_status = 'absent' WHERE status = 'no_show'")

    # --- rooms -------------------------------------------------------------
    op.add_column("rooms", sa.Column("room_type", sa.String(length=20), nullable=False, server_default="talk"))
    op.create_check_constraint("ck_rooms_type", "rooms", "room_type IN ('talk','play')")
    for code, floor, rtype in ROOMS:
        op.execute(
            sa.text(
                "INSERT INTO rooms (name, floor, room_code, room_type, has_special_equipment) "
                "SELECT :name, :floor, :code, :rtype, :special "
                "WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_code = :code)"
            ).bindparams(
                name=f"{code} {'兒童遊戲室' if rtype == 'play' else '晤談室'}",
                floor=floor, code=code, rtype=rtype, special=(rtype == "play"),
            )
        )
    # 已存在的診間不會被上面的 INSERT 覆寫，類型要另外校正
    # （2C／2E 在既有 seed 裡就有，會停在 server_default 的 'talk'）
    op.execute(
        sa.text("UPDATE rooms SET room_type = 'play', has_special_equipment = true "
                "WHERE room_code IN ('2C','2E')")
    )
    op.execute(
        sa.text("UPDATE rooms SET room_type = 'talk' WHERE room_code NOT IN ('2C','2E')")
    )

    # --- holidays ----------------------------------------------------------
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("holiday_date", name="uq_holiday_date"),
    )

    # --- 額度三態流轉的回填 -------------------------------------------------
    # Phase 1a 建欄位時把未使用的全部放進 reserved；現在把「已排定但未執行」
    # 的預約從 reserved 移到 booked，讓三態反映真實情況。
    op.execute(
        """
        WITH b AS (
            SELECT quota_id, count(*) AS n
            FROM appointments
            WHERE quota_id IS NOT NULL AND status = 'booked'
            GROUP BY quota_id
        )
        UPDATE case_institution_quotas q
        SET booked_count = LEAST(b.n, q.reserved_count),
            reserved_count = q.reserved_count - LEAST(b.n, q.reserved_count)
        FROM b WHERE b.quota_id = q.id
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE case_institution_quotas "
        "SET reserved_count = reserved_count + booked_count, booked_count = 0"
    )
    op.drop_table("holidays")
    op.drop_constraint("ck_rooms_type", "rooms", type_="check")
    op.drop_column("rooms", "room_type")

    op.drop_constraint("ck_appointments_transport_fee", "appointments", type_="check")
    op.drop_constraint("ck_appointments_checkin_status", "appointments", type_="check")
    op.drop_constraint("fk_appointments_checked_in_by", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointments_transport_fee", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointments_plan", "appointments", type_="foreignkey")
    for col in ("is_intake", "hourly_rate", "checked_in_by", "checked_in_at", "checkin_status",
                "outreach_location", "forwarded_at", "notify_admin_to_forward", "video_link",
                "transport_fee_option_id", "transport_fee", "plan_id", "fee_item"):
        op.drop_column("appointments", col)
