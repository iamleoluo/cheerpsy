"""帳冊的讀取端點不得寫資料。

起因是實機驗證時發現的：只是打開 /daily 與 /ar 兩個頁面（沒有按任何按鈕），
儀表板的「本月場次」就從 44 跳到 58、營收從 $87,500 跳到 $113,500。

原因是 routers/ledger.py 的五個 GET 端點各自呼叫了 materialize_due_appointments()，
而那支函式會 **db.commit()**：把逾時未報到的預約標成 arrived、產生 session_record、
並且 **消耗機構額度**。也就是說「看一眼帳冊」等於「幫個案簽到並扣掉他的機構補助次數」。

危害不只是報表數字不可重現：
  · GET 不具冪等性，重試／預取／重複渲染都會改資料
  · Next.js 會 prefetch 路由，所以沒有人真的進到頁面也可能改到帳
  · 產生的是**假的出席紀錄**，而額度扣掉之後要人工回補

正確的觸發點是行政在日報表按「執行日結」（POST /ledger/settle），
那條路徑保留不動。這支測試把「讀不能寫」釘住。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User

client = TestClient(app)


@pytest.fixture()
def overdue(db):
    """一筆「時間已經過去、但沒人按過報到」的預約——正是會被自動結算掉的那種。"""
    admin = User(email="ro_admin@test.local", password_hash=hash_password("x"),
                 name="唯讀測試管理員", role="admin", user_code="A820")
    ther = User(email="ro_t@test.local", password_hash=hash_password("x"),
                name="唯讀測試心理師", role="therapist", user_code="T820",
                commission_rate=Decimal("0.70"))
    db.add_all([admin, ther])
    db.flush()

    room = Room(name="ro room", floor=1, room_code="RO-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    case = Case(name="唯讀測試個案", therapist_id=ther.id, funding_source="self_pay",
                status="ongoing", case_number="99RO00001")
    db.add(case)
    db.flush()

    start = datetime.now(timezone.utc) - timedelta(days=2)
    appt = Appointment(
        appointment_number="RO-A1", case_id=case.id, therapist_id=ther.id, room_id=room.id,
        time_range=DateTimeTZRange(start, start + timedelta(hours=1)),
        status="booked", check_in_status="pending",
        session_type="in_person", amount=Decimal("2000"),
    )
    db.add(appt)
    db.flush()
    return {"db": db, "admin": admin, "appt": appt}


READ_ENDPOINTS = [
    "/ledger",
    "/ledger/pending-docs",
    "/ledger/self-pay-unpaid",
    "/ledger/self-pay-all",
    "/ledger/self-pay-cases",
]


class TestReadsDoNotMutate:
    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_get_does_not_settle_overdue_appointment(self, overdue, http_db, path, monkeypatch):
        db, appt = overdue["db"], overdue["appt"]
        from app.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: overdue["admin"]
        try:
            res = client.get(path)
            assert res.status_code == 200, res.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        db.refresh(appt)
        # 預約仍然是「待報到」，沒有被偷偷標成已到
        assert appt.status == "booked"
        assert appt.check_in_status == "pending"
        assert appt.checked_in_at is None
        # 也沒有憑空長出一筆場次紀錄
        assert db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).count() == 0


class TestExplicitSettlementStillWorks:
    def test_post_settle_materializes(self, overdue, http_db):
        """把讀取的副作用拿掉之後，明確的日結路徑必須照常運作。"""
        db, appt = overdue["db"], overdue["appt"]
        from app.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: overdue["admin"]
        try:
            res = client.post("/ledger/settle", json={})
            assert res.status_code == 200, res.text
            assert res.json()["executed"] >= 1
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        db.refresh(appt)
        assert appt.status == "executed"
        assert appt.check_in_status == "arrived"
        assert db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).count() == 1
