"""流失預警的四種情況。

這支是在把 /churn 從 N+1 改寫成單一聚合查詢時補的——原本完全沒有測試，
而那支的語意其實有四個分支（沒預約／很久沒來／最近來過／已約好下次），
靠讀程式碼很難確定改寫有沒有保住全部四種。

原本的實作還有一段更危險的：把 tstzrange **轉成字串再用逗號切開**來取
結束時間，解析失敗就靜靜當成「沒有預約」——那會讓個案無聲無息地從名單上
消失，而且不會有任何錯誤。這些測試同時把那個行為釘死在正確的一側。
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg2.extras import DateTimeTZRange

import app.models  # noqa: F401 — 註冊全部 mapper
from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.user import User

client = TestClient(app)


@pytest.fixture()
def ctx(db):
    admin = User(email="churn_admin@test.local", password_hash=hash_password("x"),
                 name="流失測試管理員", role="admin", user_code="A960")
    therapist = User(email="churn_t@test.local", password_hash=hash_password("x"),
                     name="流失測試心理師", role="therapist", user_code="T960")
    room = Room(name="churn room", floor=1, room_code="CH-1A", use_type="general", size="normal")
    db.add_all([admin, therapist, room])
    db.flush()
    return {
        "admin": admin, "therapist": therapist, "room": room,
        "headers": {"Authorization": "Bearer " + create_access_token(
            {"sub": str(admin.id), "role": "admin", "name": admin.name})},
    }


def _case(db, ctx, name: str) -> Case:
    c = Case(name=name, status="ongoing", funding_source="self_pay",
             therapist_id=ctx["therapist"].id, billing_cycle="once",
             phone="0900000000", created_by=ctx["admin"].id)
    db.add(c)
    db.flush()
    return c


def _appt(db, ctx, case: Case, days_ago: float, status: str = "executed") -> Appointment:
    start = datetime.now(timezone.utc) - timedelta(days=days_ago)
    a = Appointment(
        appointment_number=f"R-CH-{case.id}-{int(days_ago)}",
        case_id=case.id, therapist_id=ctx["therapist"].id, room_id=ctx["room"].id,
        session_type="in_person", amount=2000, status=status,
        time_range=DateTimeTZRange(start, start + timedelta(hours=1)),
        created_by=ctx["admin"].id,
    )
    db.add(a)
    db.flush()
    return a


def _names(resp) -> set[str]:
    return {r["case_name"] for r in resp.json()}


class TestChurnBranches:
    def test_case_with_no_appointment_at_all_is_flagged(self, db, http_db, ctx):
        """建了檔但一次都沒排 —— 最該被追的一種，卻也最容易被漏掉。"""
        c = _case(db, ctx, "從沒排過預約")
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        assert r.status_code == 200, r.text
        assert "從沒排過預約" in _names(r)
        row = next(x for x in r.json() if x["case_id"] == c.id)
        # 「沒有預約」與「很久沒來」要分得開：前者沒有天數可算
        assert row["last_appointment_date"] is None
        assert row["days_since_last"] is None

    def test_long_gap_is_flagged_with_day_count(self, db, http_db, ctx):
        c = _case(db, ctx, "很久沒來")
        _appt(db, ctx, c, days_ago=90)
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        row = next(x for x in r.json() if x["case_id"] == c.id)
        assert row["days_since_last"] >= 89
        assert row["last_appointment_date"] is not None

    def test_recent_visit_is_not_flagged(self, db, http_db, ctx):
        """最後一次落在門檻與現在之間 —— 最近才來過，不算流失。"""
        c = _case(db, ctx, "上週才來過")
        _appt(db, ctx, c, days_ago=7)
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        assert "上週才來過" not in _names(r)

    def test_future_booking_is_not_flagged_even_after_a_long_gap(self, db, http_db, ctx):
        """**這條最容易寫錯**：很久沒來，但已經約好下次了。

        只看「最後一次結束時間」而不看未來預約的話，這種個案會被錯誤地列進
        追蹤名單——行政打電話過去，對方說「我下週就要去了」。
        """
        c = _case(db, ctx, "久沒來但已約下次")
        _appt(db, ctx, c, days_ago=120)
        _appt(db, ctx, c, days_ago=-14, status="booked")   # 兩週後
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        assert "久沒來但已約下次" not in _names(r)

    def test_cancelled_appointment_does_not_count_as_contact(self, db, http_db, ctx):
        """取消的預約不算來過 —— 人根本沒出現。"""
        c = _case(db, ctx, "只有取消的預約")
        _appt(db, ctx, c, days_ago=5, status="cancelled")
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        assert "只有取消的預約" in _names(r)

    def test_closed_case_is_never_flagged(self, db, http_db, ctx):
        """已結案的不是流失，是結束了。"""
        c = _case(db, ctx, "已結案")
        c.status = "closed"
        _appt(db, ctx, c, days_ago=200)
        db.commit()
        r = client.get("/churn?inactive_days=30", headers=ctx["headers"])
        assert "已結案" not in _names(r)

    def test_inactive_days_parameter_moves_the_line(self, db, http_db, ctx):
        c = _case(db, ctx, "45 天沒來")
        _appt(db, ctx, c, days_ago=45)
        db.commit()
        assert "45 天沒來" in _names(client.get("/churn?inactive_days=30", headers=ctx["headers"]))
        assert "45 天沒來" not in _names(client.get("/churn?inactive_days=60", headers=ctx["headers"]))
