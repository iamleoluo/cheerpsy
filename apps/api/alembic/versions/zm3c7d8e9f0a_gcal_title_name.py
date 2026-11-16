"""Google 日曆同步：事件標題格式新增 (d) type_room_name，並設為預設

只改 clinic_settings 的 check constraint 與欄位預設值，不刪表、不刪資料。
既有那一列若「從沒被管理員改過」（updated_by_user_id 為空，也就是仍是舊預設 (c)），改成新預設 (d)；
管理員明確選過的值一律不動。downgrade 把 (d) 的列改回 (c)，並還原 constraint 與預設。

Revision ID: zm3c7d8e9f0a
Revises: zl2b6c7d8e9f
"""

from alembic import op

revision = "zm3c7d8e9f0a"
down_revision = "zl2b6c7d8e9f"
branch_labels = None
depends_on = None

OLD = "event_title_format IN ('type_room', 'type_room_code', 'type_room_abbrev')"
NEW = "event_title_format IN ('type_room', 'type_room_code', 'type_room_abbrev', 'type_room_name')"


def upgrade() -> None:
    op.drop_constraint("ck_clinic_settings_title_format", "clinic_settings", type_="check")
    op.create_check_constraint("ck_clinic_settings_title_format", "clinic_settings", NEW)
    op.alter_column("clinic_settings", "event_title_format", server_default="type_room_name")
    op.execute("UPDATE clinic_settings SET event_title_format = 'type_room_name' "
               "WHERE event_title_format = 'type_room_abbrev' AND updated_by_user_id IS NULL")


def downgrade() -> None:
    op.execute("UPDATE clinic_settings SET event_title_format = 'type_room_abbrev' WHERE event_title_format = 'type_room_name'")
    op.alter_column("clinic_settings", "event_title_format", server_default="type_room_abbrev")
    op.drop_constraint("ck_clinic_settings_title_format", "clinic_settings", type_="check")
    op.create_check_constraint("ck_clinic_settings_title_format", "clinic_settings", OLD)
