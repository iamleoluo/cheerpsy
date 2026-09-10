"""GET /room-calendar — 診間日曆聚合端點（V2升級計畫 02 §5.1）。

重點全部在 **is_settled（整格轉灰）**，因為那不是一條規則而是三條
（02 §4.3 / 03 §整格轉灰時機），而前端第一版只實作了其中一條：

    自費需收款案   收款 ＋ 開立收據都完成才轉灰
    自費月結案     按完「已到」即轉灰（不需收款／收據）
    機構案         已到 ＋ 應收結清 ＋ 行政流程提醒全部勾完

「轉灰」的意思是「這格今天不用再碰了」，所以未到**不轉灰**（03：未到的格子
維持紅底），而月結案雖然沒收到半毛錢卻要轉灰——因為它今天本來就不收。
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.models.appointment import Appointment
from app.models.appointment_admin_task import AppointmentAdminTask
from app.models.case import Case
from app.models.receipt import Receipt
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.utils.tz import day_range_utc
from app.routers.room_calendar import room_calendar

TODAY = date(2026, 6, 15)


@pytest.fixture()
def env(db):
    admin = User(email="rc_admin@test.local", password_hash=hash_password("x"),
                 name="日曆測試管理員", role="admin", user_code="A830")
    ther = User(email="rc_t@test.local", password_hash=hash_password("x"),
                name="日曆測試心理師", role="therapist", user_code="T830",
                commission_rate=Decimal("0.70"))
    db.add_all([admin, ther])
    db.flush()
    room = Room(name="rc room", floor=2, room_code="RC-2A", use_type="general", size="normal")
    db.add(room)
    db.flush()
    return {"db": db, "admin": admin, "ther": ther, "room": room}


def _appt(env, *, billing_cycle="once", funding="self_pay", check_in="arrived", hour=10):
    db = env["db"]
    case = Case(name=f"日曆個案{hour}", therapist_id=env["ther"].id, funding_source=funding,
                status="ongoing", case_number=f"99RC0{hour:04d}", billing_cycle=billing_cycle)
    db.add(case)
    db.flush()
    # 從「台北當日」的 UTC 起點往後推，而不是直接寫 UTC 時鐘——
    # 台北 = UTC+8，直接寫 UTC 16:00 會掉到隔天的台北日，格子就查不到了。
    start = day_range_utc(TODAY)[0] + timedelta(hours=hour)
    a = Appointment(
        appointment_number=f"RC-{hour}", case_id=case.id, therapist_id=env["ther"].id,
        room_id=env["room"].id,
        time_range=DateTimeTZRange(start, start + timedelta(hours=1)),
        status="executed" if check_in == "arrived" else "booked",
        check_in_status=check_in, session_type="in_person",
        amount=Decimal("2000"), funding_source=funding,
    )
    db.add(a)
    db.flush()
    return a, case


def _record(env, appt, *, collected=False, case_payable=None):
    db = env["db"]
    sr = SessionRecord(
        appointment_id=appt.id, session_date=TODAY, case_id=appt.case_id,
        therapist_id=appt.therapist_id, amount=Decimal("2000"),
        session_type="in_person", funding_source=appt.funding_source,
        payment_status="paid" if collected else "unpaid",
        case_payable=case_payable,
        copay_collected_at=datetime.now(timezone.utc) if collected else None,
    )
    db.add(sr)
    db.flush()
    return sr


def _receipt(env, sr):
    r = Receipt(receipt_no=f"A-RC-{sr.id}", session_record_id=sr.id,
                amount=sr.amount, status="issued", created_by=env["admin"].id)
    env["db"].add(r)
    env["db"].flush()
    return r


def _cell(env, appt):
    res = room_calendar(q=TODAY, floor="all", user=env["admin"], db=env["db"])
    return next(c for c in res["cells"] if c["appointment_id"] == appt.id)


class TestSelfPayPerVisit:
    """自費需收款：收款 ＋ 開據都完成才轉灰。"""

    def test_arrived_only_is_not_settled(self, env):
        a, _ = _appt(env, hour=10)
        _record(env, a)
        assert _cell(env, a)["is_settled"] is False

    def test_collected_without_receipt_is_not_settled(self, env):
        a, _ = _appt(env, hour=11)
        _record(env, a, collected=True)
        assert _cell(env, a)["is_settled"] is False

    def test_collected_and_receipted_is_settled(self, env):
        a, _ = _appt(env, hour=12)
        sr = _record(env, a, collected=True)
        _receipt(env, sr)
        cell = _cell(env, a)
        assert cell["is_settled"] is True
        assert cell["issued_receipt_no"] == f"A-RC-{sr.id}"


class TestSelfPayMonthly:
    """自費月結：按完已到即轉灰，不需收款／收據。"""

    def test_arrived_is_settled_without_payment(self, env):
        a, _ = _appt(env, billing_cycle="monthly", hour=13)
        _record(env, a)  # 未收款、無收據
        cell = _cell(env, a)
        assert cell["billing_cycle"] == "monthly"
        assert cell["is_settled"] is True

    def test_not_arrived_is_not_settled(self, env):
        a, _ = _appt(env, billing_cycle="monthly", check_in="pending", hour=14)
        assert _cell(env, a)["is_settled"] is False


class TestInstitution:
    """機構案：已到 ＋ 應收結清 ＋ 行政流程提醒全勾。"""

    def test_pending_admin_task_blocks_settlement(self, env):
        a, _ = _appt(env, funding="institution", hour=15)
        _record(env, a, collected=True, case_payable=Decimal("400"))
        env["db"].add(AppointmentAdminTask(appointment_id=a.id, title="確認轉介單", is_done=False))
        env["db"].flush()
        cell = _cell(env, a)
        assert cell["admin_tasks_pending"] == 1
        assert cell["is_settled"] is False

    def test_all_tasks_done_and_collected_is_settled(self, env):
        a, _ = _appt(env, funding="institution", hour=16)
        _record(env, a, collected=True, case_payable=Decimal("400"))
        env["db"].add(AppointmentAdminTask(appointment_id=a.id, title="確認轉介單", is_done=True))
        env["db"].flush()
        assert _cell(env, a)["is_settled"] is True

    def test_full_subsidy_needs_no_collection(self, env):
        """自付額 0 的全額補助方案視為已結清。"""
        a, _ = _appt(env, funding="institution", hour=17)
        _record(env, a, collected=False, case_payable=Decimal("0"))
        assert _cell(env, a)["is_settled"] is True

    def test_unpaid_copay_blocks_settlement(self, env):
        a, _ = _appt(env, funding="institution", hour=18)
        _record(env, a, collected=False, case_payable=Decimal("400"))
        assert _cell(env, a)["is_settled"] is False


class TestNoShow:
    def test_no_show_never_settles(self, env):
        """03：未到的格子維持紅底，不轉灰。"""
        a, _ = _appt(env, check_in="no_show", hour=19)
        assert _cell(env, a)["is_settled"] is False


class TestReadOnly:
    def test_get_does_not_materialize(self, env):
        """讀取端點不得順手結算（02 §4.1；先前 /ledger 五個 GET 就是犯這個）。"""
        a, _ = _appt(env, check_in="pending", hour=9)
        room_calendar(q=TODAY, floor="all", user=env["admin"], db=env["db"])
        env["db"].refresh(a)
        assert a.check_in_status == "pending"
        assert a.status == "booked"
        assert env["db"].query(SessionRecord).filter(
            SessionRecord.appointment_id == a.id).count() == 0


class TestFloorFilter:
    def test_floor_filter_narrows_cells(self, env):
        a, _ = _appt(env, hour=20)
        assert any(c["appointment_id"] == a.id
                   for c in room_calendar(q=TODAY, floor="2", user=env["admin"], db=env["db"])["cells"])
        assert not any(c["appointment_id"] == a.id
                       for c in room_calendar(q=TODAY, floor="3", user=env["admin"], db=env["db"])["cells"])
