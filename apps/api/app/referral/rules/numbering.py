"""派案碼：YYMMDD + 3 位流水號，例 260801001。建立需求表時產生一次，
見 cheerpsy_v7_spec_extracted.md「媒合管理」編號規則。

實際配號在 app/services/numbering.py（06 P0 的序列表）。
"""

from datetime import date

from sqlalchemy.orm import Session

from app.services import numbering


def generate_referral_code(db: Session, on_date: date | None = None) -> str:
    return numbering.next_referral_code(db, on_date=on_date or date.today())
