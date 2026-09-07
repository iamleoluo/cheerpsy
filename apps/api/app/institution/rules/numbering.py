"""核銷案編號：YYMM + 流水2碼，如 202607-01。見 07 §4.3 / §6.1 附錄。

沿用主系統既有慣例用 COUNT(*)+1（見 01 §C+ 的併發提醒，此處先維持一致寫法，
待主系統的 services/numbering.py 統一改為序列/重試時一併處理，不在本次
子系統骨架範圍內單獨解決)。
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.institution.models.claim_case import InstClaimCase


def next_claim_no(db: Session, on_date: date | None = None) -> str:
    d = on_date or date.today()
    prefix = d.strftime("%Y%m")
    count = (
        db.query(func.count(InstClaimCase.id))
        .filter(InstClaimCase.claim_no.like(f"{prefix}-%"))
        .scalar()
        or 0
    )
    return f"{prefix}-{count + 1:02d}"
