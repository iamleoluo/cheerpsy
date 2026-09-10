"""GET /dashboard/todos — 營運總覽的今日待辦佇列（V2升級計畫 11 §4.1）。

這支端點的價值不在「查得到資料」，而在**查出來的每一列都是今天真的要做的事**。
第一版寫完拿真實資料集一跑就吐出 119 筆——跟改寫前那四張 SELECT COUNT 一樣沒用。
所以這裡的測試重點全部是「哪些東西不該出現」：

  · 已入帳的核銷批次即使有缺件也不算待辦（實測 49 筆缺件有 45 筆屬於這種）
  · 額度用罄但近期沒有預約的個案不算待辦（用完半年了沒人會去處理）
  · 同一類超過 MAX_PER_KIND 筆要收成一列，不能把長尾攤開
  · 心理師不進本頁
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.routers.dashboard import MAX_PER_KIND, dashboard_todos


@pytest.fixture()
def env(db):
    """一組最小的行政／心理師／機構／個案，供各測試堆待辦上去。"""
    admin = User(email="td_admin@test.local", password_hash=hash_password("x"),
                 name="待辦測試管理員", role="admin", user_code="A810")
    ther = User(email="td_t@test.local", password_hash=hash_password("x"),
                name="待辦測試心理師", role="therapist", user_code="T810",
                commission_rate=Decimal("0.70"))
    db.add_all([admin, ther])
    db.flush()

    inst = Institution(name="待辦測試機構")
    db.add(inst)
    db.flush()

    contract = InstContract(institution_id=inst.id, name="待辦測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()

    plan = InstPlan(contract_id=contract.id, name="待辦測試方案",
                    quota_unit="count", default_quota_limit_numeric=6,
                    compensation_mode="commission", created_by=admin.id)
    db.add(plan)
    db.flush()

    room = Room(name="td room", floor=1, room_code="TD-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    case = Case(name="待辦測試個案", therapist_id=ther.id, funding_source="institution",
                institution_id=inst.id, status="ongoing", case_number="99TD00001")
    db.add(case)
    db.flush()

    return {"db": db, "admin": admin, "ther": ther, "inst": inst,
            "plan": plan, "room": room, "case": case}


def _kinds(res):
    return [t["kind"] for t in res["todos"]]


class TestRoleScoping:
    def test_therapist_gets_nothing(self, env):
        """心理師不進本頁（v7：改看心理師版「我的今日」）。"""
        res = dashboard_todos(user=env["ther"], db=env["db"])
        assert res["todos"] == []


class TestClaimDocGate:
    def _record(self, env, batch_status):
        db = env["db"]
        batch = ClaimBatch(batch_number=f"TD-{batch_status}", type="institution",
                           status=batch_status, institution_id=env["inst"].id,
                           total_amount=Decimal("0"))
        db.add(batch)
        db.flush()
        rec = SessionRecord(
            session_date=date.today() - timedelta(days=30),
            therapist_id=env["ther"].id, case_id=env["case"].id,
            amount=Decimal("2000"), payment_status="claimed",
            session_type="in_person", funding_source="institution",
            claim_batch_id=batch.id, therapist_doc_submitted_at=None,
        )
        db.add(rec)
        db.flush()
        return batch

    def test_open_batch_missing_docs_is_a_todo(self, env):
        self._record(env, "collecting")
        res = dashboard_todos(user=env["admin"], db=env["db"])
        assert "claim_doc" in _kinds(res)

    def test_received_batch_is_not_a_todo(self, env):
        """已入帳的批次即使缺件也不是今天要處理的事。

        這條是實測逼出來的：真實資料集裡 49 個有缺件的批次有 45 個已經
        received，全列出來等於用雜訊把真正要處理的 4 個蓋掉。
        """
        self._record(env, "received")
        res = dashboard_todos(user=env["admin"], db=env["db"])
        assert "claim_doc" not in _kinds(res)


class TestQuotaNeedsUpcomingVisit:
    def _enroll(self, env, reserved):
        e = InstEnrollment(case_id=env["case"].id, plan_id=env["plan"].id,
                           quota_unit="count", quota_limit=Decimal("6"),
                           reserved_count=Decimal(str(reserved)),
                           used_count=Decimal("6") - Decimal(str(reserved)),
                           status="active")
        env["db"].add(e)
        env["db"].flush()
        return e

    def _appointment(self, env, days_ahead):
        start = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        appt = Appointment(
            appointment_number=f"TD-A{days_ahead}", case_id=env["case"].id,
            therapist_id=env["ther"].id, room_id=env["room"].id,
            time_range=DateTimeTZRange(start, start + timedelta(hours=1)),
            status="booked", check_in_status="pending",
            session_type="in_person", amount=Decimal("2000"),
        )
        env["db"].add(appt)
        env["db"].flush()
        return appt

    def test_exhausted_quota_with_upcoming_visit_is_a_todo(self, env):
        self._enroll(env, 0)
        self._appointment(env, days_ahead=3)
        res = dashboard_todos(user=env["admin"], db=env["db"])
        assert "quota" in _kinds(res)

    def test_exhausted_quota_without_upcoming_visit_is_not(self, env):
        """額度用完但這個人接下來不會來——沒有任何行政動作要做。"""
        self._enroll(env, 0)
        res = dashboard_todos(user=env["admin"], db=env["db"])
        assert "quota" not in _kinds(res)

    def test_upcoming_visit_beyond_lookahead_is_not(self, env):
        self._enroll(env, 0)
        self._appointment(env, days_ahead=90)
        res = dashboard_todos(user=env["admin"], db=env["db"])
        assert "quota" not in _kinds(res)


class TestLongTailCollapses:
    def test_overflow_row_replaces_the_tail(self, env):
        """超過 MAX_PER_KIND 筆就收成一列，總筆數不隨資料量線性成長。"""
        db = env["db"]
        n = MAX_PER_KIND + 4
        for i in range(n):
            rec = SessionRecord(
                session_date=date.today() - timedelta(days=30 + i),
                therapist_id=env["ther"].id, case_id=env["case"].id,
                amount=Decimal("1000"), payment_status="unpaid",
                session_type="in_person", funding_source="self_pay",
                copay_collected_at=None,
            )
            db.add(rec)
        db.flush()

        res = dashboard_todos(user=env["admin"], db=db)
        unpaid = [t for t in res["todos"] if t["kind"] == "unpaid"]
        assert len(unpaid) == MAX_PER_KIND + 1

        overflow = [t for t in unpaid if t["id"].endswith(":more")]
        assert len(overflow) == 1
        assert overflow[0]["count"] == n - MAX_PER_KIND
        # 收合列永遠排在該類最後
        assert overflow[0]["urgency"] == min(t["urgency"] for t in unpaid)

    def test_sorted_by_urgency_descending(self, env):
        res = dashboard_todos(user=env["admin"], db=env["db"])
        urgencies = [t["urgency"] for t in res["todos"]]
        assert urgencies == sorted(urgencies, reverse=True)
