"""流失預警：太久沒有預約的活躍個案。

「流失」不是一個存在資料庫裡的狀態——`cases` 沒有 `churn_risk` 這個值，
也不該有。它是一個**即時算出來的判斷**：活躍個案（initial／ongoing）的
最後一次預約已經結束超過 N 天，而且沒有排在未來的預約。

判斷條件攤開來只有兩種情況：

    最後一次預約的結束時間 < 門檻      → 曾經來過，之後就沒再來
    完全沒有預約                       → 建了檔但一次都沒排

反過來說，最後一次預約落在門檻與現在之間（最近才來過），或是還有未來的
預約（已經約好下次），兩種都不算流失。
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/churn", tags=["churn"])


@router.get("")
def churn_warning_list(
    inactive_days: int = Query(default=30, ge=7, le=180),
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    """一句聚合查詢算完，不逐案再查。

    改寫的原因是資料量放大之後量到的：原本先撈出全部活躍個案，再**逐案**查
    最後一次預約、再逐案查心理師——1,140 個案就是 2,000 多次查詢，
    這支端點要 0.56 秒，是同一批端點裡其他支的 50 倍。

    順帶拿掉了更危險的一段：原本把 `tstzrange` **轉成字串再用逗號切開**來取
    結束時間（`str(r).split(",")[1].rstrip(")")`），解析失敗就靜靜當成沒有預約
    ——那會讓個案無聲無息地從流失名單上消失。範圍型別的上界交給 `upper()`，
    那才是它的用途。
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = now - timedelta(days=inactive_days)

    rows = db.execute(
        text("""
        SELECT c.id            AS case_id,
               c.name          AS case_name,
               u.name          AS therapist_name,
               c.phone         AS phone,
               c.status        AS status,
               c.funding_source AS funding_source,
               x.last_end      AS last_end
          FROM cases c
          LEFT JOIN users u ON u.id = c.therapist_id
          LEFT JOIN LATERAL (
                SELECT max(upper(a.time_range)) AS last_end
                  FROM appointments a
                 WHERE a.case_id = c.id
                   AND a.status IN ('booked', 'executed')
               ) x ON true
         WHERE c.status IN ('initial', 'ongoing')
           -- 沒有預約，或最後一次已經結束超過門檻。
           -- （落在門檻與現在之間＝最近來過；晚於現在＝已約好下次，兩種都不算）
           AND (x.last_end IS NULL OR x.last_end < :cutoff)
         ORDER BY x.last_end NULLS FIRST
        """),
        {"cutoff": cutoff},
    ).mappings().all()

    result = []
    for r in rows:
        last_end = r["last_end"]
        result.append({
            "case_id": r["case_id"],
            "case_name": r["case_name"],
            "therapist_name": r["therapist_name"],
            "phone": r["phone"],
            "status": r["status"],
            "funding_source": r["funding_source"],
            "last_appointment_date": last_end.date().isoformat() if last_end else None,
            # 從沒排過預約的排最前面（原本用 9999 當排序鍵，這裡由 SQL 的
            # NULLS FIRST 處理，前端仍拿得到 None 以區分「沒有」與「很久」）
            "days_since_last": (now - last_end).days if last_end else None,
        })
    return result
