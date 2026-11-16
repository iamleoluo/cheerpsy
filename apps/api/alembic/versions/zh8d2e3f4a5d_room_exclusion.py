"""診間重疊改由資料庫保證（exclusion constraint）

只新增、不刪表、不改欄位。

- 先掃描現有資料：同一診間、時段重疊、且都是 booked／executed 的預約。
  有重疊就 RAISE 並列出清單，migration 失敗，不會建出一半的約束。
  上線前請先在複本跑 apps/api/scripts/list_overlaps.py，請行政處理完再 migrate。
- 約束：room_id 相同且 time_range 重疊，只對 booked／executed 生效，
  所以取消與未到（no_show）的場次會釋出診間。
- 寫成 EXCLUDE USING gist (int4range(room_id, room_id, '[]') WITH &&, time_range WITH &&)，
  不使用 `room_id WITH =`，因此不需要 btree_gist extension。

Revision ID: zh8d2e3f4a5d
Revises: zg7c1d2e3f4c
"""

import sqlalchemy as sa
from alembic import op

revision = "zh8d2e3f4a5d"
down_revision = "zg7c1d2e3f4c"
branch_labels = None
depends_on = None

CONSTRAINT = "ex_appointments_room"
MAX_LISTED = 50

SCAN_SQL = """
SELECT r.room_code,
       a.appointment_number AS a_no, lower(a.time_range) AS a_start, upper(a.time_range) AS a_end,
       b.appointment_number AS b_no, lower(b.time_range) AS b_start, upper(b.time_range) AS b_end
FROM appointments a
JOIN appointments b
  ON a.room_id = b.room_id AND a.id < b.id AND a.time_range && b.time_range
JOIN rooms r ON r.id = a.room_id
WHERE a.room_id IS NOT NULL
  AND a.status IN ('booked', 'executed')
  AND b.status IN ('booked', 'executed')
ORDER BY r.room_code, lower(a.time_range)
"""


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(SCAN_SQL)).fetchall()
    if rows:
        lines = [
            f"  診間 {r.room_code}：{r.a_no} [{r.a_start} ~ {r.a_end}) 與 {r.b_no} [{r.b_start} ~ {r.b_end})"
            for r in rows[:MAX_LISTED]
        ]
        more = f"\n  …另有 {len(rows) - MAX_LISTED} 組" if len(rows) > MAX_LISTED else ""
        raise RuntimeError(
            f"appointments 有 {len(rows)} 組診間時段重疊，無法建立 {CONSTRAINT}。"
            "請先由行政改期或取消其中一筆（可用 apps/api/scripts/list_overlaps.py 列出清單）：\n"
            + "\n".join(lines) + more
        )

    op.execute(
        f"""
        ALTER TABLE appointments
        ADD CONSTRAINT {CONSTRAINT}
        EXCLUDE USING gist (
            int4range(room_id, room_id, '[]') WITH &&,
            time_range WITH &&
        )
        WHERE (room_id IS NOT NULL AND status IN ('booked', 'executed'))
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE appointments DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
