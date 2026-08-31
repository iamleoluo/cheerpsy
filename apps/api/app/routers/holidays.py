from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.holiday import Holiday
from app.models.user import User

router = APIRouter(prefix="/holidays", tags=["holidays"])

# 2026 年台灣國定假日（行政院人事行政總處公告）
# 批次預約時只做提醒、不自動跳過（原型 booking 定案②）
SEED_2026 = [
    ("2026-01-01", "開國紀念日"),
    ("2026-01-02", "調整放假"),
    ("2026-02-14", "小年夜"),
    ("2026-02-15", "除夕"),
    ("2026-02-16", "春節"),
    ("2026-02-17", "春節"),
    ("2026-02-18", "春節"),
    ("2026-02-19", "調整放假"),
    ("2026-02-20", "調整放假"),
    ("2026-02-27", "調整放假"),
    ("2026-02-28", "和平紀念日"),
    ("2026-04-03", "調整放假"),
    ("2026-04-04", "兒童節"),
    ("2026-04-05", "清明節"),
    ("2026-04-06", "調整放假"),
    ("2026-05-01", "勞動節"),
    ("2026-06-19", "端午節"),
    ("2026-09-25", "中秋節"),
    ("2026-10-09", "調整放假"),
    ("2026-10-10", "國慶日"),
]


class HolidayIn(BaseModel):
    holiday_date: date
    name: str


@router.get("")
def list_holidays(
    year: int | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Holiday)
    if year:
        q = q.filter(
            Holiday.holiday_date >= date(year, 1, 1),
            Holiday.holiday_date <= date(year, 12, 31),
        )
    return [
        {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}
        for h in q.order_by(Holiday.holiday_date).all()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_holiday(
    body: HolidayIn,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    if db.query(Holiday).filter(Holiday.holiday_date == body.holiday_date).first():
        raise HTTPException(status_code=400, detail="該日期已存在")
    h = Holiday(holiday_date=body.holiday_date, name=body.name.strip())
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(
    holiday_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    h = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(h)
    db.commit()


@router.post("/seed/{year}")
def seed_year(
    year: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """匯入該年度的國定假日。目前只內建 2026 年，其他年度請手動新增。"""
    if year != 2026:
        raise HTTPException(
            status_code=400,
            detail=f"尚未內建 {year} 年的假日表，請用「新增」逐筆建立",
        )
    added = 0
    for d, name in SEED_2026:
        dd = date.fromisoformat(d)
        if not db.query(Holiday).filter(Holiday.holiday_date == dd).first():
            db.add(Holiday(holiday_date=dd, name=name))
            added += 1
    db.commit()
    return {"year": year, "added": added, "total": len(SEED_2026)}
