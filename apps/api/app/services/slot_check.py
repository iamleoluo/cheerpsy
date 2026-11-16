"""診間時段檢查（預約與活動共用）。

規則：只有 booked／executed 的預約佔用診間；cancelled、no_show 釋出。
活動（events）佔用含場佈時間。
錯誤訊息只寫診間代號與衝突的時段，不帶個案、心理師或活動名稱。

資料庫層另有 exclusion constraint（ex_appointments_room）擋 race；
flush_or_409 會把違反約束（SQLSTATE 23P01）轉成同樣格式的 409。
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.room import Room

TZ = timezone(timedelta(hours=8))  # 診所在台灣
OCCUPYING = ("booked", "executed")
EXCLUSION_VIOLATION = "23P01"
UNIQUE_VIOLATION = "23505"


def _fmt(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return "該時段"
    s = start.astimezone(TZ)
    if end is None:
        return s.strftime("%m/%d %H:%M")
    e = end.astimezone(TZ)
    return f"{s:%m/%d %H:%M}–{e:%H:%M}"


def _room_code(db: Session, room_id: int) -> str:
    room = db.query(Room).filter(Room.id == room_id).first()
    return room.room_code if room else str(room_id)


def find_room_conflict(
    db: Session, room_id: int, start: datetime, end: datetime,
    exclude_appointment_id: int | None = None, exclude_event_id: int | None = None,
):
    """回傳 (kind, conflict_start, conflict_end)；沒有衝突回 None。kind 為 appointment 或 event。"""
    sql = """
        SELECT lower(time_range) AS s, upper(time_range) AS e FROM appointments
        WHERE room_id = :room_id
          AND status IN ('booked', 'executed')
          AND time_range && tstzrange(:start, :end)
    """
    params: dict = {"room_id": room_id, "start": start, "end": end}
    if exclude_appointment_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_appointment_id
    row = db.execute(text(sql + " ORDER BY lower(time_range) LIMIT 1"), params).first()
    if row:
        return "appointment", row.s, row.e

    q = db.query(
        func.coalesce(Event.setup_start_at, Event.start_at), Event.end_at
    ).filter(
        Event.room_id == room_id,
        func.tstzrange(func.coalesce(Event.setup_start_at, Event.start_at), Event.end_at)
        .op("&&")(func.tstzrange(start, end)),
    )
    if exclude_event_id is not None:
        q = q.filter(Event.id != exclude_event_id)
    ev = q.first()
    if ev:
        return "event", ev[0], ev[1]
    return None


def _conflict_error(db: Session, room_id: int, start: datetime, end: datetime, found) -> HTTPException:
    code = _room_code(db, room_id)
    if found is None:  # race：約束擋下了，但重新查已查不到（對方剛好又被改掉）
        return HTTPException(status_code=409, detail=f"診間 {code} 在 {_fmt(start, end)} 已被使用")
    kind, c_start, c_end = found
    what = "已有活動（含場佈時間）" if kind == "event" else "已被使用"
    return HTTPException(status_code=409, detail=f"診間 {code} 在 {_fmt(c_start, c_end)} {what}")


def assert_room_active(db: Session, room_id: int | None) -> None:
    """診間存在且未停用；停用的診間不能再新增預約（歷史預約不受影響）。"""
    if not room_id:
        return
    room = db.query(Room).filter(Room.id == room_id).first()
    if room is None:
        raise HTTPException(status_code=404, detail="診間不存在")
    if not room.is_active:
        raise HTTPException(status_code=400, detail=f"診間 {room.room_code} 已停用，無法預約")


def assert_room_free(
    db: Session, room_id: int | None, start: datetime, end: datetime,
    exclude_appointment_id: int | None = None,
) -> None:
    """診間在該時段沒有 booked／executed 預約，也沒有活動；否則 409。"""
    if not room_id:
        return
    found = find_room_conflict(db, room_id, start, end, exclude_appointment_id=exclude_appointment_id)
    if found:
        raise _conflict_error(db, room_id, start, end, found)


def flush_or_409(db: Session, room_id: int | None, start: datetime, end: datetime,
                 exclude_appointment_id: int | None = None) -> None:
    """flush；若資料庫的 exclusion constraint 擋下（並行寫入），轉成 409。"""
    try:
        db.flush()
    except IntegrityError as exc:
        code = getattr(exc.orig, "pgcode", None)
        if code not in (EXCLUSION_VIOLATION, UNIQUE_VIOLATION) or not room_id:
            raise
        db.rollback()
        found = find_room_conflict(db, room_id, start, end, exclude_appointment_id=exclude_appointment_id)
        # 23P01 一定是診間約束。23505（唯一鍵）在並行建立時也可能先被觸發：
        # 同一時刻有人搶走同一時段，重查就找得到對方；找不到才是真的別種唯一鍵錯誤，原樣丟出。
        if code == EXCLUSION_VIOLATION or found is not None:
            raise _conflict_error(db, room_id, start, end, found) from exc
        raise


# ---- 心理師與個案的時段衝突 ------------------------------------------------
# 規則：同一位心理師、或同一個個案（含伴侶案成員）在 booked／executed 預約的時段重疊 → 409。
# 訊息只寫時段，不寫別人的個案姓名、心理師姓名。
# 資料庫層暫時沒有對應的 EXCLUDE 約束（待正式資料以 scripts/list_overlaps.py 清乾淨後再加），
# 所以並行寫入的 race 目前只靠這裡的檢查擋。


def case_participants(db: Session, case_ids) -> set[int]:
    """一組個案實際牽涉到的個案 id：自己、所屬的伴侶案、伴侶案的其他成員。"""
    ids = {int(c) for c in case_ids if c}
    if not ids:
        return set()
    rows = db.execute(
        text("""
            SELECT couple_case_id, member_case_id FROM case_members
             WHERE couple_case_id = ANY(:ids) OR member_case_id = ANY(:ids)
        """),
        {"ids": list(ids)},
    ).all()
    out = set(ids)
    for couple_id, member_id in rows:
        out.add(couple_id)
        out.add(member_id)
    return out


def assert_therapist_free(
    db: Session, therapist_id: int | None, start: datetime, end: datetime,
    exclude_appointment_id: int | None = None,
) -> None:
    """該心理師在時段內沒有其他 booked／executed 預約；否則 409。"""
    if not therapist_id:
        return
    sql = """
        SELECT lower(time_range) AS s, upper(time_range) AS e FROM appointments
         WHERE therapist_id = :tid AND status IN ('booked', 'executed')
           AND time_range && tstzrange(:start, :end)
    """
    params: dict = {"tid": therapist_id, "start": start, "end": end}
    if exclude_appointment_id is not None:
        sql += " AND id != :ex"
        params["ex"] = exclude_appointment_id
    row = db.execute(text(sql + " ORDER BY lower(time_range) LIMIT 1"), params).first()
    if row:
        raise HTTPException(status_code=409, detail=f"心理師在 {_fmt(row.s, row.e)} 已有其他預約")


def assert_case_free(
    db: Session, case_ids, start: datetime, end: datetime,
    exclude_appointment_id: int | None = None,
) -> None:
    """該個案（含伴侶案與其成員）在時段內沒有其他 booked／executed 預約；否則 409。
    case_ids 傳預約的 case_id（付款方）與 couple_case_id。"""
    ids = case_participants(db, case_ids)
    if not ids:
        return
    sql = """
        SELECT lower(time_range) AS s, upper(time_range) AS e FROM appointments
         WHERE (case_id = ANY(:ids) OR couple_case_id = ANY(:ids))
           AND status IN ('booked', 'executed')
           AND time_range && tstzrange(:start, :end)
    """
    params: dict = {"ids": list(ids), "start": start, "end": end}
    if exclude_appointment_id is not None:
        sql += " AND id != :ex"
        params["ex"] = exclude_appointment_id
    row = db.execute(text(sql + " ORDER BY lower(time_range) LIMIT 1"), params).first()
    if row:
        raise HTTPException(status_code=409, detail=f"個案在 {_fmt(row.s, row.e)} 已有其他預約")


def assert_therapist_available(db: Session, therapist_id: int | None, start: datetime, end: datetime) -> None:
    """心理師在時段內沒有「這段不接案」；否則 409。訊息只寫時段，不帶原因（原因只有本人與行政看得到）。"""
    if not therapist_id:
        return
    row = db.execute(
        text("""
            SELECT lower(time_range) AS s, upper(time_range) AS e FROM therapist_time_off
             WHERE therapist_id = :tid AND time_range && tstzrange(:start, :end)
             ORDER BY lower(time_range) LIMIT 1
        """),
        {"tid": therapist_id, "start": start, "end": end},
    ).first()
    if row:
        raise HTTPException(status_code=409, detail=f"心理師在 {_fmt(row.s, row.e)} 不接案")
