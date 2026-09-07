"""P1 出席驅動：PUT /appointments/{id}/check-in 的端到端測試。

見 01 §A1、02 §4.1、08_實作進度與系統架構現況.html §8 下一步第1項。

涵蓋：已到/未到兩條路徑、機構額度的 consume()/release()、權限矩陣
（現場限行政、視訊/外展限心理師本人）、重複報到擋下、以及最重要的
回歸測試——materialize_due_appointments() 不能重複處理已人工報到的
預約、也不能誤判 no_show 的預約為「沒人管、自動結算」。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.adapter import InstitutionFundingProvider
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.settlement import materialize_due_appointments
from psycopg2.extras import DateTimeTZRange

client = TestClient(app)


def _seed(db):
    admin = User(email="ci_admin@test.local", password_hash=hash_password("x"), name="報到測試管理員", role="admin", user_code="A600")
    staff = User(email="ci_staff@test.local", password_hash=hash_password("x"), name="報到測試行政", role="staff", user_code="S600")
    therapist = User(
        email="ci_t@test.local", password_hash=hash_password("x"), name="報到測試心理師",
        role="therapist", user_code="T600", commission_rate=Decimal("0.70"),
    )
    other_therapist = User(
        email="ci_t2@test.local", password_hash=hash_password("x"), name="另一位心理師",
        role="therapist", user_code="T601", commission_rate=Decimal("0.70"),
    )
    db.add_all([admin, staff, therapist, other_therapist])
    db.flush()

    inst = Institution(name="報到測試機構")
    db.add(inst)
    db.flush()

    room = Room(name="ci room", floor=1, room_code="CI-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    case = Case(
        name="報到測試個案", therapist_id=therapist.id, funding_source="institution",
        institution_id=inst.id, status="ongoing", case_number="99CI00001",
    )
    db.add(case)
    db.flush()

    contract = InstContract(institution_id=inst.id, name="報到測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()
    plan = InstPlan(
        contract_id=contract.id, name="報到測試方案", quota_unit="count", default_quota_limit_numeric=3,
        compensation_mode="commission", case_receipt_required=True, case_receipt_item_name="場地費",
        claim_group_key="報到測試方案", claim_timing="monthly", created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=200, label="固定價"))
    db.flush()

    provider = InstitutionFundingProvider()
    enrollment = provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    db.commit()

    return {
        "admin": admin, "staff": staff, "therapist": therapist, "other_therapist": other_therapist,
        "room": room, "case": case, "plan": plan, "enrollment_id": enrollment.enrollment_id,
        "admin_token": create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name}),
        "staff_token": create_access_token({"sub": str(staff.id), "role": "staff", "name": staff.name}),
        "therapist_token": create_access_token({"sub": str(therapist.id), "role": "therapist", "name": therapist.name}),
        "other_therapist_token": create_access_token({"sub": str(other_therapist.id), "role": "therapist", "name": other_therapist.name}),
    }


def _create_appt(db, ctx, session_type="in_person", minutes_from_now=60, plan=True):
    start = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    end = start + timedelta(hours=1)
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
    payload = {
        "case_id": ctx["case"].id, "therapist_id": ctx["therapist"].id,
        "session_type": session_type,
        "start_time": start.isoformat(), "end_time": end.isoformat(),
    }
    if session_type == "in_person":
        payload["room_id"] = ctx["room"].id
    if plan:
        payload["plan_id"] = ctx["plan"].id
    else:
        payload["amount"] = 2000
        payload["funding_source"] = "self_pay"
    r = client.post("/appointments", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestArrivedPath:
    def test_admin_checks_in_in_person_creates_session_record_immediately(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="in_person", minutes_from_now=60)  # 還沒到時間

        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['admin_token']}"},
            json={"status": "arrived"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["check_in_status"] == "arrived"
        assert body["status"] == "executed"
        assert body["checked_in_at"] is not None

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is not None, "按已到應該立刻建立 session_record，不用等時間到"
        assert sr.plan_id == ctx["plan"].id
        assert sr.case_payable == Decimal("200.00")
        assert sr.institution_payable == Decimal("1400.00")

        row = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert row.used_count == 1, "consume() 應該已經被呼叫"

    def test_double_checkin_rejected(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="in_person", minutes_from_now=60)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r1 = client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
        assert r1.status_code == 200
        r2 = client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
        assert r2.status_code == 400
        assert "已經報到過" in r2.json()["detail"]


class TestNoShowPath:
    def test_no_show_releases_quota_and_keeps_status_booked(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="in_person", minutes_from_now=60)
        row_before = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        reserved_before = row_before.reserved_count

        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['admin_token']}"},
            json={"status": "no_show", "no_show_reason": "unreachable", "no_show_note": "電話沒人接"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["check_in_status"] == "no_show"
        assert body["status"] == "booked", "未到不轉 cancelled，供對帳追蹤（01 §C3）"
        assert body["no_show_reason"] == "unreachable"

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is None, "未到不應該產生應收/session_record"

        row_after = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert row_after.reserved_count == reserved_before + 1, "還原為已預留，不是釋回（個案仍保有額度）"


class TestPermissions:
    def test_therapist_cannot_checkin_own_in_person(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="in_person", minutes_from_now=60)
        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['therapist_token']}"},
            json={"status": "arrived"},
        )
        assert r.status_code == 403
        assert "櫃檯" in r.json()["detail"]

    def test_therapist_can_checkin_own_online(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="online", minutes_from_now=60)
        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['therapist_token']}"},
            json={"status": "arrived"},
        )
        assert r.status_code == 200, r.text

    def test_therapist_cannot_checkin_others_appointment(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="online", minutes_from_now=60)
        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['other_therapist_token']}"},
            json={"status": "arrived"},
        )
        assert r.status_code == 403
        assert "自己的預約" in r.json()["detail"]

    def test_staff_can_checkin_in_person(self, db, http_db):
        ctx = _seed(db)
        appt_id = _create_appt(db, ctx, session_type="in_person", minutes_from_now=60)
        r = client.put(
            f"/appointments/{appt_id}/check-in",
            headers={"Authorization": f"Bearer {ctx['staff_token']}"},
            json={"status": "arrived"},
        )
        assert r.status_code == 200


class TestMaterializeDoesNotDoubleProcess:
    """回歸測試：鎖住這輪重構的兩個關鍵行為。"""

    def test_materialize_skips_already_checked_in_appointment(self, db, http_db):
        """appt 已經被人工按過「已到」，時間過了之後 materialize 不該再處理一次
        （不會重複建立 session_record、不會重複扣額度）。"""
        ctx = _seed(db)
        # 建一筆已經過去的預約，直接用 check-in 端點報到（而非讓它自然過期被 materialize 撿到）
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        end = start + timedelta(minutes=5)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post("/appointments", headers=headers, json={
            "case_id": ctx["case"].id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
            "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "plan_id": ctx["plan"].id,
        })
        appt_id = r.json()["id"]
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})

        result = materialize_due_appointments(db)
        assert result["materialized"] == 0, "已經人工報到過的預約不該被 materialize 重新處理"

        row = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert row.used_count == 1, "額度只該被扣一次，不是兩次"

    def test_materialize_never_processes_no_show_appointment(self, db, http_db):
        """這是這輪重構要修的那個 bug 本身：未到的預約 status 仍是 'booked'，
        若 materialize 沒有排除 check_in_status != 'pending'，時間一過就會被
        誤判成「沒人管、自動結算」，生出一筆不該存在的 session_record。"""
        ctx = _seed(db)
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        end = start + timedelta(minutes=5)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post("/appointments", headers=headers, json={
            "case_id": ctx["case"].id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
            "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "plan_id": ctx["plan"].id,
        })
        appt_id = r.json()["id"]
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "no_show", "no_show_reason": "unreachable"})

        result = materialize_due_appointments(db)
        assert result["materialized"] == 0

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is None, "no_show 的預約絕對不能被 materialize 生出 session_record"

        appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
        assert appt.status == "booked"
        assert appt.check_in_status == "no_show"

    def test_materialize_still_catches_forgotten_appointments(self, db, http_db):
        """補登安全網還是要能用：沒人手動報到、時間已經過去很久的預約，
        materialize 仍然要撿起來（行政忘了按已到的情境）。"""
        ctx = _seed(db)
        start = datetime.now(timezone.utc) - timedelta(minutes=40)
        end = start + timedelta(minutes=5)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post("/appointments", headers=headers, json={
            "case_id": ctx["case"].id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
            "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "plan_id": ctx["plan"].id,
        })
        appt_id = r.json()["id"]
        # 沒有呼叫 check-in——模擬行政忘了按

        result = materialize_due_appointments(db)
        assert result["materialized"] == 1

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is not None
        appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
        assert appt.check_in_status == "arrived", "補登路徑也要把 check_in_status 補成 arrived，保持狀態一致"
