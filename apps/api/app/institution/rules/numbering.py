"""核銷案容器編號：{YYYYMM}-{流水2碼}，如 202607-01。見 07 §4.3 / §6.1 附錄。

實際配號在 app/services/numbering.py（06 P0 的序列表）。這支保留為子系統的
薄封裝，讓子系統內部的呼叫端不必知道主系統模組的路徑。
"""

from datetime import date

from sqlalchemy.orm import Session

from app.services import numbering


def next_claim_no(db: Session, on_date: date | None = None) -> str:
    return numbering.next_claim_no(db, on_date=on_date or date.today())
