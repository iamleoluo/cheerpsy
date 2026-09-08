"""病歷號產生。實際配號邏輯在 app/services/numbering.py（06 P0 的序列表）；
這裡只負責「從個案身上取出編號需要的材料」——身分證末兩碼、以及要用哪一天
的年份當前綴。

`on_date` 預設今天，但一定要能傳：補歷史資料時，去年初診的個案應該拿到去年
年份的病歷號，不是灌資料當下的年份。
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.case import Case
from app.services import numbering
from app.utils.encryption import decrypt_national_id


def generate_case_number(db: Session, case: Case, on_date: date | None = None) -> str:
    """一般個案：{YY}{流水4碼}{身分證末2碼}，例 26000145。"""
    national_id = decrypt_national_id(case.national_id_encrypted)
    d = on_date or case.initial_visit_date or date.today()
    return numbering.next_case_number(db, on_date=d, national_id_last2=national_id[-2:])


def generate_couple_number(db: Session, on_date: date | None = None) -> str:
    """伴侶案專用編號（無身分證）。格式：C{YY}{流水4碼}，例 C260003。"""
    return numbering.next_couple_number(db, on_date=on_date or date.today())
