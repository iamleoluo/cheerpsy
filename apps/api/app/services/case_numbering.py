from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.case import Case
from app.utils.encryption import decrypt_national_id


def generate_case_number(db: Session, case: Case) -> str:
    """Generate formal case number: {YY}{SEQ4}{last2digits_of_national_id}"""
    yy = str(datetime.now().year % 100).zfill(2)
    count = db.query(func.count(Case.id)).filter(Case.case_number.like(f"{yy}%")).scalar() or 0
    seq = str(count + 1).zfill(4)
    national_id = decrypt_national_id(case.national_id_encrypted)
    last2 = national_id[-2:]
    return f"{yy}{seq}{last2}"
