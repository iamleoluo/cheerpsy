"""P0 地基修正：audit_log 欄寬、共用帳號、診間屬性

見 V2升級計畫 01_可行性研究與風險.html §C6/§C7、02_架構變更規格.html §1.1/§2。

- audit_log.operation VARCHAR(10) -> VARCHAR(32)：既有程式已寫入
  "ADMIN_VERIFY_ALL" 等超過 10 字元的值，正式環境會直接丟例外。
- audit_log.actor_name：共用帳號（實習心理師）登入時自填姓名的快照。
- users.is_shared_account / supervisor_id：共用帳號旗標與督導配對預留欄位。
- users.supervision_fee_mode / supervision_split_rate / supervision_split_amount：
  機構合約子系統場地租借 b4 用（07 §4.1），資料待心理師主檔提供。
- rooms.use_type / size：定稿要求的診間卡標籤（⭐上次使用/👶遊戲室/大間）
  需要這兩個屬性才排得出來。診間主檔本身從 13 間測試資料重建為定稿 12 間
  是「資料」層面的事，走 seed.py 的 rebuild_room_roster()，不在這支
  migration 裡動資料，只加欄位。

Revision ID: aa1a2b3c4d5f1
Revises: z2a1b2c3d4e5
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "aa1a2b3c4d5f1"
down_revision = "z2a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # audit_log
    op.alter_column("audit_log", "operation", type_=sa.String(32), existing_type=sa.String(10))
    op.add_column("audit_log", sa.Column("actor_name", sa.String(100), nullable=True))

    # users
    op.add_column(
        "users",
        sa.Column("is_shared_account", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("supervisor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("users", sa.Column("supervision_fee_mode", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("supervision_split_rate", sa.Numeric(4, 2), nullable=True))
    op.add_column("users", sa.Column("supervision_split_amount", sa.Numeric(10, 2), nullable=True))

    # rooms
    op.add_column(
        "rooms",
        sa.Column("use_type", sa.String(20), nullable=False, server_default="general"),
    )
    op.add_column(
        "rooms",
        sa.Column("size", sa.String(20), nullable=False, server_default="normal"),
    )


def downgrade() -> None:
    op.drop_column("rooms", "size")
    op.drop_column("rooms", "use_type")

    op.drop_column("users", "supervision_split_amount")
    op.drop_column("users", "supervision_split_rate")
    op.drop_column("users", "supervision_fee_mode")
    op.drop_column("users", "supervisor_id")
    op.drop_column("users", "is_shared_account")

    op.drop_column("audit_log", "actor_name")
    op.alter_column("audit_log", "operation", type_=sa.String(10), existing_type=sa.String(32))
