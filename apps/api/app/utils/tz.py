"""台北時區工具（P0，V2升級計畫 02 §9）。

背景：settlement.py 等多處用 UTC 午夜切「今天」，台北時間會落在早上 08:00 ——
剛好是營業時段 08:00–22:00 的第一格，對日曆／日報表／報到這類「當日」判斷是硬傷。

用法：所有「今天」「當日區間」的計算一律呼叫這支模組，不要自己重寫
`datetime.now(timezone.utc)` 或 `date.today()` 再手動加減時區。

尚未完成的清理（見 01 §C+ 附錄，列出但本次未動）：
    settlement.py:162、dashboard.py、notifications.py、reports.py、churn.py
    裡仍有幾處直接用 date.today() / datetime.now(timezone.utc) 的日界計算，
    之後汰換時直接替換成本模組對應函式即可，行為不變。
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
UTC = timezone.utc


def now_local() -> datetime:
    """目前時間，帶 Asia/Taipei tzinfo。"""
    return datetime.now(UTC).astimezone(TAIPEI)


def today_local() -> date:
    """台北時間的「今天」日期。"""
    return now_local().date()


def day_range_utc(d: date) -> tuple[datetime, datetime]:
    """給定一個台北時間的日期，回傳該日 00:00–翌日00:00 對應的 UTC 起訖（皆含 tzinfo）。

    用於「查某一天」的 SQL range 過濾，例如：
        start, end = day_range_utc(target)
        appointments.filter(Appointment.time_range.op("&&")(tstzrange(start, end)))
    """
    start_local = datetime.combine(d, time.min, tzinfo=TAIPEI)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def to_local_date(dt: datetime) -> date:
    """把一個帶 tzinfo（通常是 UTC，來自 DB）的 datetime 轉成台北時間的日期。

    這是取代「appt.time_range.lower.date()」這類寫法的正確方式——
    後者是直接取 UTC 日期，深夜時段的預約會被歸到錯誤的一天。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(TAIPEI).date()
