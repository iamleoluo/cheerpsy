from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.referral.models.referral import Referral


def generate_referral_code(db: Session) -> str:
    """派案碼：YYMMDD + 3 位流水號，例 260801001。建立需求表時產生一次，
    見 cheerpsy_v7_spec_extracted.md「媒合管理」編號規則。"""
    prefix = datetime.now().strftime("%y%m%d")
    count = db.query(func.count(Referral.id)).filter(Referral.referral_code.like(f"{prefix}%")).scalar() or 0
    seq = str(count + 1).zfill(3)
    return f"{prefix}{seq}"
