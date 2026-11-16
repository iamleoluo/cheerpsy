"""唯讀檢查：列出金額為 0／NULL、機構預約自付額為 NULL，或同一預約有多筆有效 session_records 的預約。

只執行 SELECT，不改任何資料。用法（需設定 DATABASE_URL）：
    python scripts/check_amounts.py            # 列表
    python scripts/check_amounts.py --strict   # 有任何項目時結束碼為 1（可放進檢查流程）
"""

import os
import sys

import sqlalchemy as sa

QUERY = """
SELECT a.id, a.appointment_number, lower(a.time_range) AS start_time, a.status, a.funding_source,
       a.amount, a.self_pay_amount,
       CASE
         WHEN a.amount IS NULL THEN '金額為 NULL'
         WHEN a.amount = 0 THEN '金額為 0'
         WHEN a.funding_source = 'institution' AND a.self_pay_amount IS NULL THEN '機構預約自付額未設定'
         ELSE '有多筆有效 session_records（回填取最新一筆，請確認）'
       END AS problem
  FROM appointments a
 WHERE a.amount IS NULL OR a.amount = 0
    OR (a.funding_source = 'institution' AND a.self_pay_amount IS NULL)
    OR (SELECT count(*) FROM session_records s WHERE s.appointment_id = a.id AND s.is_void = false) > 1
 ORDER BY lower(a.time_range), a.id
"""


def main(argv: list[str]) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("請設定 DATABASE_URL", file=sys.stderr)
        return 2
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = conn.execute(sa.text(QUERY)).fetchall()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for r in rows:
        print(f"#{r.id}\t{r.appointment_number}\t{r.start_time:%Y-%m-%d %H:%M}\t{r.status}\t"
              f"{r.funding_source}\t總額={r.amount}\t自付={r.self_pay_amount}\t{r.problem}")
    print(f"共 {len(rows)} 筆需要確認")
    return 1 if (rows and "--strict" in argv) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
