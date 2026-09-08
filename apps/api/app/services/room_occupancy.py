"""跨表的診間佔用檢查。

診間現在有兩種佔用者：一般預約（appointments）與場地租借（venue_rentals）。
兩張表各自有 EXCLUDE USING GIST 擋自己表內的重疊，但**跨表沒辦法用單一
約束表達**——Postgres 的 EXCLUDE 只能作用在一張表上。

所以跨表這一層由這支模組在應用層擋，並由 scripts/check_invariants.py 的
room_overlap 檢查當守門員（生成器與 CI 都會跑）。這是「兩層並存」那套做法
的延伸：這層給人看得懂的訊息，DB 層給同表內的正確性保證，不變量檢查器
負責定期確認跨表也沒破。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


def find_conflicts(
    db: Session,
    room_id: int,
    start: datetime,
    end: datetime,
    exclude_appointment_id: int | None = None,
    exclude_rental_id: int | None = None,
) -> list[dict]:
    """回傳所有佔住這個診間這段時間的東西。空 list 代表可以用。"""
    conflicts: list[dict] = []

    sql = (
        "SELECT a.id, a.appointment_number AS ref, u.name AS who, a.time_range::text AS tr "
        "  FROM appointments a LEFT JOIN users u ON u.id = a.therapist_id "
        " WHERE a.room_id = :room_id AND a.status <> 'cancelled' "
        "   AND a.time_range && tstzrange(:start, :end)"
    )
    params: dict = {"room_id": room_id, "start": start.isoformat(), "end": end.isoformat()}
    if exclude_appointment_id is not None:
        sql += " AND a.id <> :ex_appt"
        params["ex_appt"] = exclude_appointment_id
    for row in db.execute(text(sql), params).mappings():
        conflicts.append({"kind": "appointment", **dict(row)})

    sql2 = (
        "SELECT v.id, v.rental_no AS ref, v.renter_name AS who, v.time_range::text AS tr "
        "  FROM venue_rentals v "
        " WHERE v.room_id = :room_id AND v.status <> 'cancelled' "
        "   AND v.time_range && tstzrange(:start, :end)"
    )
    params2: dict = {"room_id": room_id, "start": start.isoformat(), "end": end.isoformat()}
    if exclude_rental_id is not None:
        sql2 += " AND v.id <> :ex_rental"
        params2["ex_rental"] = exclude_rental_id
    for row in db.execute(text(sql2), params2).mappings():
        conflicts.append({"kind": "venue_rental", **dict(row)})

    return conflicts


def assert_free(
    db: Session,
    room_id: int,
    start: datetime,
    end: datetime,
    exclude_appointment_id: int | None = None,
    exclude_rental_id: int | None = None,
) -> None:
    """撞到就丟 409，訊息帶上是被誰佔住的——行政要知道去找誰喬。"""
    conflicts = find_conflicts(db, room_id, start, end,
                               exclude_appointment_id, exclude_rental_id)
    if not conflicts:
        return
    c = conflicts[0]
    label = "預約" if c["kind"] == "appointment" else "場地租借"
    raise HTTPException(
        status_code=409,
        detail=f"該診間時段已被佔用（{label} {c['ref']}．{c['who'] or '—'}），請改時間或換診間",
    )
