"""唯讀：列出 appointments 裡「診間」與「心理師」的時段重疊（booked／executed）。

用途：加 exclusion constraint 之前，先請行政把重疊清掉。
  - 診間重疊：migration zh8d2e3f4a5d 會在有重疊時失敗。
  - 心理師重疊：目前還沒有約束（之後另開 migration），先清乾淨才能加。

只有 SELECT，並且開在 READ ONLY 交易裡，不會改任何資料。
輸出只有預約編號、診間代號、心理師代號與時段，不含個案姓名或其他個資。

用法（在 apps/api 目錄）：
    DATABASE_URL=postgresql://... python scripts/list_overlaps.py
    python scripts/list_overlaps.py --since 2026-01-01      # 只看某日之後
    python scripts/list_overlaps.py --limit 200

結束碼：0 沒有重疊；1 有重疊；2 連線或執行錯誤。
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

TZ = timezone(timedelta(hours=8))

ROOM_SQL = """
SELECT r.room_code AS room,
       a.id AS a_id, a.appointment_number AS a_no, a.status AS a_status, a.time_range AS a_range,
       b.id AS b_id, b.appointment_number AS b_no, b.status AS b_status, b.time_range AS b_range
FROM appointments a
JOIN appointments b
  ON a.room_id = b.room_id AND a.id < b.id AND a.time_range && b.time_range
JOIN rooms r ON r.id = a.room_id
WHERE a.room_id IS NOT NULL
  AND a.status IN ('booked', 'executed') AND b.status IN ('booked', 'executed')
  AND (CAST(:since AS timestamptz) IS NULL OR upper(a.time_range) > :since)
ORDER BY r.room_code, lower(a.time_range)
LIMIT :limit
"""

THERAPIST_SQL = """
SELECT u.user_code AS therapist,
       a.id AS a_id, a.appointment_number AS a_no, a.status AS a_status, a.time_range AS a_range, a.room_id AS a_room,
       b.id AS b_id, b.appointment_number AS b_no, b.status AS b_status, b.time_range AS b_range, b.room_id AS b_room
FROM appointments a
JOIN appointments b
  ON a.therapist_id = b.therapist_id AND a.id < b.id AND a.time_range && b.time_range
JOIN users u ON u.id = a.therapist_id
WHERE a.status IN ('booked', 'executed') AND b.status IN ('booked', 'executed')
  AND (CAST(:since AS timestamptz) IS NULL OR upper(a.time_range) > :since)
ORDER BY u.user_code, lower(a.time_range)
LIMIT :limit
"""


def fmt(rng) -> str:
    if rng is None or rng.lower is None:
        return "?"
    s = rng.lower.astimezone(TZ)
    e = rng.upper.astimezone(TZ) if rng.upper else None
    return f"{s:%Y-%m-%d %H:%M}–{e:%H:%M}" if e else f"{s:%Y-%m-%d %H:%M}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="只看結束時間晚於此日期的預約，格式 YYYY-MM-DD（台灣時間）")
    ap.add_argument("--limit", type=int, default=1000, help="每一種最多列出幾組（預設 1000）")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("請設定環境變數 DATABASE_URL", file=sys.stderr)
        return 2
    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=TZ)

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            params = {"since": since, "limit": args.limit}
            room_rows = conn.execute(text(ROOM_SQL), params).fetchall()
            th_rows = conn.execute(text(THERAPIST_SQL), params).fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"執行失敗：{e}", file=sys.stderr)
        return 2

    print(f"== 診間重疊：{len(room_rows)} 組（booked／executed） ==")
    for r in room_rows:
        print(f"診間 {r.room}：{r.a_no}[{r.a_status}] {fmt(r.a_range)}  <->  {r.b_no}[{r.b_status}] {fmt(r.b_range)}")

    print(f"\n== 心理師重疊：{len(th_rows)} 組（booked／executed） ==")
    for r in th_rows:
        rooms = f"診間 id {r.a_room or '—'} / {r.b_room or '—'}"
        print(f"心理師 {r.therapist}：{r.a_no}[{r.a_status}] {fmt(r.a_range)}  <->  {r.b_no}[{r.b_status}] {fmt(r.b_range)}（{rooms}）")

    if len(room_rows) >= args.limit or len(th_rows) >= args.limit:
        print(f"\n注意：已達 --limit {args.limit}，實際可能更多。", file=sys.stderr)
    total = len(room_rows) + len(th_rows)
    print(f"\n合計 {total} 組。" + ("沒有重疊。" if total == 0 else "請行政改期或取消其中一筆。"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
