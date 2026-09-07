"""DB 層房間衝突防護（EXCLUDE USING GIST）測試。

見 aa5a2b3c4d5f5_room_conflict_gist.py、_flush_with_conflict_guard()
（routers/appointments.py）、08 §8 下一步第1項。

_check_room_conflict() 是應用層 SELECT-then-INSERT，天生有 TOCTOU 競態窗口；
GIST 約束才是真正的防線。pytest 單執行緒無法模擬真併發，這裡改為直接繞過
應用層檢查——手動 db.add() 一筆會與既有預約重疊的 Appointment，直接呼叫
_flush_with_conflict_guard()，驗證它把 IntegrityError 轉成乾淨的 409，而
不是讓 Postgres 原始例外洩漏成 500。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.user import User
from app.routers.appointments import _flush_with_conflict_guard


def _seed(db):
    therapist = User(
        email="gist_t@test.local", password_hash=hash_password("x"), name="GIST測試心理師",
        role="therapist", user_code="T900", commission_rate=Decimal("0.70"),
    )
    db.add(therapist)
    db.flush()

    room = Room(name="gist room", floor=1, room_code="GIST-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    case = Case(
        name="GIST測試個案", therapist_id=therapist.id, funding_source="self_pay",
        status="ongoing", case_number="99GIST001",
    )
    db.add(case)
    db.flush()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=1)
    existing = Appointment(
        case_id=case.id, therapist_id=therapist.id, room_id=room.id,
        time_range=DateTimeTZRange(start, end), status="booked",
        session_type="in_person", amount=Decimal("1000"),
        appointment_number="GIST-EXIST-001",
    )
    db.add(existing)
    db.flush()

    return {
        "therapist_id": therapist.id, "room_id": room.id, "case_id": case.id,
        "existing_id": existing.id, "start": start, "end": end,
    }


class TestConflictGuardTranslatesIntegrityErrorTo409:
    def test_overlapping_insert_raises_409_not_raw_500(self, db):
        """繞過 _check_room_conflict()，直接讓 GIST 約束攔截，驗證
        _flush_with_conflict_guard() 把 IntegrityError 轉成乾淨的 409。"""
        ctx = _seed(db)
        conflicting = Appointment(
            case_id=ctx["case_id"], therapist_id=ctx["therapist_id"], room_id=ctx["room_id"],
            time_range=DateTimeTZRange(
                ctx["start"] + timedelta(minutes=30), ctx["end"] + timedelta(minutes=30)
            ),
            status="booked", session_type="in_person", amount=Decimal("1000"),
            appointment_number="GIST-CONFLICT-001",
        )
        db.add(conflicting)

        with pytest.raises(HTTPException) as exc_info:
            _flush_with_conflict_guard(db)

        assert exc_info.value.status_code == 409
        assert "資料庫層攔截" in exc_info.value.detail

    def test_non_overlapping_insert_succeeds(self, db):
        """確認 guard 不會誤擋不衝突的新預約（回歸測試，避免約束條件寫錯）。"""
        ctx = _seed(db)
        non_conflicting = Appointment(
            case_id=ctx["case_id"], therapist_id=ctx["therapist_id"], room_id=ctx["room_id"],
            time_range=DateTimeTZRange(ctx["end"], ctx["end"] + timedelta(hours=1)),
            status="booked", session_type="in_person", amount=Decimal("1000"),
            appointment_number="GIST-OK-001",
        )
        db.add(non_conflicting)

        _flush_with_conflict_guard(db)  # 不應拋出

        assert non_conflicting.id is not None

    def test_cancelled_appointment_does_not_block(self, db):
        """status='cancelled' 的預約不參與約束（跟 _check_room_conflict 的
        WHERE 條件一致），確認取消後的時段真的能重新排。"""
        ctx = _seed(db)
        existing = db.query(Appointment).filter(Appointment.id == ctx["existing_id"]).first()
        existing.status = "cancelled"
        db.flush()

        rebooked = Appointment(
            case_id=ctx["case_id"], therapist_id=ctx["therapist_id"], room_id=ctx["room_id"],
            time_range=DateTimeTZRange(ctx["start"], ctx["end"]),
            status="booked", session_type="in_person", amount=Decimal("1000"),
            appointment_number="GIST-REBOOK-001",
        )
        db.add(rebooked)

        _flush_with_conflict_guard(db)  # 不應拋出

        assert rebooked.id is not None
