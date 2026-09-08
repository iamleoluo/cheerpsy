"""P4 新排程實體：加時、視訊連結、個案請假、行政流程提醒、場地租借、雲燈教室。

這一批是「文件寫了但從來沒建」的功能（06 P4/P6、02 §1.2）。重點驗三件
最容易做錯的事：

  ① 加時回寫預約時間時撞到鄰場要**擋下**（01 §C1 裁示，不自動擠掉別人）
  ② 場地租借與一般預約**共用診間**，衝突要跨表看
  ③ 請假不等於未到——時段釋出、額度還回去，但不收機構未到補助
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
from app.models.appointment_admin_task import AppointmentAdminTask
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User

client = TestClient(app)
provider = InstitutionFundingProvider()


def _seed(db, with_checklist=False, no_show_fee=None):
    admin = User(email="p4_admin@test.local", password_hash=hash_password("x"),
                 name="P4測試管理員", role="admin", user_code="A940")
    therapist = User(email="p4_t@test.local", password_hash=hash_password("x"),
                     name="P4測試心理師", role="therapist", user_code="T940",
                     commission_rate=Decimal("0.70"))
    db.add_all([admin, therapist])
    db.flush()
    inst = Institution(name="P4測試機構")
    db.add(inst)
    db.flush()
    room = Room(name="p4 room", floor=1, room_code="P4-1A", use_type="general", size="normal")
    room2 = Room(name="p4 room2", floor=1, room_code="P4-1B", use_type="general", size="normal")
    db.add_all([room, room2])
    db.flush()
    case = Case(name="P4測試個案", therapist_id=therapist.id, funding_source="institution",
                institution_id=inst.id, status="ongoing", case_number="99P400001")
    db.add(case)
    db.flush()
    contract = InstContract(institution_id=inst.id, name="P4測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()
    plan = InstPlan(
        contract_id=contract.id, name="P4測試方案", quota_unit="count",
        default_quota_limit_numeric=8, compensation_mode="commission",
        claim_group_key="P4測試", no_show_fee_numeric=no_show_fee, created_by=admin.id,
        admin_checklist='["台南市民同意書(第一次)", "個案基本資料表"]' if with_checklist else None,
        therapist_checklist='["初次晤談紀錄"]' if with_checklist else None,
    )
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1800, case_payable=300, label="固定價"))
    db.flush()
    provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    db.commit()
    return {
        "admin": admin, "therapist": therapist, "case": case, "plan": plan,
        "room": room, "room2": room2, "inst": inst,
        "admin_h": {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': 'admin', 'name': admin.name})}"},
        "t_h": {"Authorization": f"Bearer {create_access_token({'sub': str(therapist.id), 'role': 'therapist', 'name': therapist.name})}"},
    }


def _book(ctx, hours_from_now, minutes=60, room=None, session_type="in_person", plan=True):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    end = start + timedelta(minutes=minutes)
    payload = {
        "case_id": ctx["case"].id, "session_type": session_type,
        "start_time": start.isoformat(), "end_time": end.isoformat(),
    }
    if session_type == "in_person":
        payload["room_id"] = (room or ctx["room"]).id
    if plan:
        payload["plan_id"] = ctx["plan"].id
    else:
        payload["amount"] = 2000
        payload["funding_source"] = "self_pay"
    r = client.post("/appointments", headers=ctx["admin_h"], json=payload)
    assert r.status_code == 201, r.text
    return r.json(), start, end


class TestAdjustDuration:
    def test_extends_time_and_recalculates_amount(self, db, http_db):
        ctx = _seed(db)
        appt, start, end = _book(ctx, hours_from_now=24)
        assert appt["amount"] == 1800.0

        r = client.put(f"/appointments/{appt['id']}/adjust-duration", headers=ctx["admin_h"], json={
            "actual_start": start.isoformat(),
            "actual_end": (start + timedelta(minutes=90)).isoformat(),
            "note": "個案情緒未穩，延長 30 分鐘",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["amount"] == 2700.0, "60 分 $1800 → 90 分應為 $2700"
        # 同步回寫預約時間，日曆上的格子才會跟著變長。
        # 比對「同一個瞬間」而不是字串——API 回的是 +08:00 表示法，測試手上的是 UTC。
        assert datetime.fromisoformat(body["end_time"]) == start + timedelta(minutes=90)

    def test_blocked_when_it_would_collide_with_next_appointment(self, db, http_db):
        """01 §C1 裁示：撞到相鄰預約就擋下，提示請洽行政——不自動擠掉下一位。"""
        ctx = _seed(db)
        first, start, end = _book(ctx, hours_from_now=24)
        # 緊接著同一診間的下一場
        _book(ctx, hours_from_now=25)

        r = client.put(f"/appointments/{first['id']}/adjust-duration", headers=ctx["admin_h"], json={
            "actual_start": start.isoformat(),
            "actual_end": (start + timedelta(minutes=90)).isoformat(),
        })
        assert r.status_code == 409, r.text
        assert "已被佔用" in r.json()["detail"]

    def test_rejected_after_payment(self, db, http_db):
        ctx = _seed(db)
        appt, start, _ = _book(ctx, hours_from_now=-2)
        client.put(f"/appointments/{appt['id']}/check-in", headers=ctx["admin_h"], json={"status": "arrived"})
        client.post(f"/appointments/{appt['id']}/payment-step", headers=ctx["admin_h"], json={"payment_method": "cash"})
        r = client.put(f"/appointments/{appt['id']}/adjust-duration", headers=ctx["admin_h"], json={
            "actual_start": start.isoformat(),
            "actual_end": (start + timedelta(minutes=90)).isoformat(),
        })
        assert r.status_code == 400
        assert "已收款" in r.json()["detail"]

    def test_syncs_ledger_amount(self, db, http_db):
        ctx = _seed(db)
        appt, start, _ = _book(ctx, hours_from_now=-3)
        client.put(f"/appointments/{appt['id']}/check-in", headers=ctx["admin_h"], json={"status": "arrived"})
        r = client.put(f"/appointments/{appt['id']}/adjust-duration", headers=ctx["admin_h"], json={
            "actual_start": start.isoformat(),
            "actual_end": (start + timedelta(minutes=30)).isoformat(),
        })
        assert r.status_code == 200, r.text
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt["id"]).first()
        db.refresh(sr)
        assert float(sr.amount) == 900.0, "帳冊金額要跟著改，否則日報表跟預約對不起來"


class TestVideoLink:
    def test_therapist_sets_link_admin_forwards(self, db, http_db):
        ctx = _seed(db)
        appt, _, _ = _book(ctx, hours_from_now=48, session_type="online")

        r = client.put(f"/appointments/{appt['id']}/video-link", headers=ctx["t_h"],
                       json={"video_link": "https://meet.example.com/abc-defg"})
        assert r.status_code == 200, r.text

        r2 = client.put(f"/appointments/{appt['id']}/video-forwarded", headers=ctx["admin_h"])
        assert r2.status_code == 200, r2.text
        a = db.query(Appointment).filter(Appointment.id == appt["id"]).first()
        db.refresh(a)
        assert a.video_link.startswith("https://")
        assert a.video_forwarded_at is not None

    def test_changing_link_resets_forwarded_flag(self, db, http_db):
        ctx = _seed(db)
        appt, _, _ = _book(ctx, hours_from_now=48, session_type="online")
        client.put(f"/appointments/{appt['id']}/video-link", headers=ctx["t_h"],
                   json={"video_link": "https://meet.example.com/one"})
        client.put(f"/appointments/{appt['id']}/video-forwarded", headers=ctx["admin_h"])
        client.put(f"/appointments/{appt['id']}/video-link", headers=ctx["t_h"],
                   json={"video_link": "https://meet.example.com/two"})
        a = db.query(Appointment).filter(Appointment.id == appt["id"]).first()
        db.refresh(a)
        assert a.video_forwarded_at is None, "換了連結就要重新轉發，否則個案收到的是舊連結"

    def test_rejected_for_in_person(self, db, http_db):
        ctx = _seed(db)
        appt, _, _ = _book(ctx, hours_from_now=48)
        r = client.put(f"/appointments/{appt['id']}/video-link", headers=ctx["t_h"],
                       json={"video_link": "https://x"})
        assert r.status_code == 400


class TestCaseLeave:
    def test_leave_releases_slot_and_quota_without_billing_fee(self, db, http_db):
        """請假 ≠ 未到：時段釋出、額度還回去，但不收機構未到補助。"""
        ctx = _seed(db, no_show_fee=800)
        appt, _, _ = _book(ctx, hours_from_now=48)
        e = db.query(InstEnrollment).filter(InstEnrollment.case_id == ctx["case"].id).first()
        db.refresh(e)
        assert e.reserved_count == 7

        r = client.put(f"/appointments/{appt['id']}/leave", headers=ctx["t_h"],
                       json={"reason": "個案臨時出差"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"

        db.expire_all()
        e = db.query(InstEnrollment).filter(InstEnrollment.case_id == ctx["case"].id).first()
        assert e.reserved_count == 8, "請假要把額度還回已預留"
        fee = db.query(SessionRecord).filter(
            SessionRecord.appointment_id == appt["id"],
            SessionRecord.fee_category == "no_show_fee",
        ).count()
        assert fee == 0, "請假不是未到，不可以跟機構請未到補助"

    def test_cannot_leave_after_checkin(self, db, http_db):
        ctx = _seed(db)
        appt, _, _ = _book(ctx, hours_from_now=-2)
        client.put(f"/appointments/{appt['id']}/check-in", headers=ctx["admin_h"], json={"status": "arrived"})
        r = client.put(f"/appointments/{appt['id']}/leave", headers=ctx["t_h"], json={})
        assert r.status_code == 400


class TestAdminTaskChecklist:
    def test_checklist_materialised_on_booking(self, db, http_db):
        ctx = _seed(db, with_checklist=True)
        appt, _, _ = _book(ctx, hours_from_now=24)
        r = client.get(f"/appointments/{appt['id']}/admin-tasks", headers=ctx["admin_h"])
        assert r.status_code == 200, r.text
        tasks = r.json()
        assert len(tasks) == 3
        assert [t["side"] for t in tasks] == ["admin", "admin", "therapist"]
        assert all(t["is_done"] is False for t in tasks)

    def test_tick_records_actor_and_time(self, db, http_db):
        ctx = _seed(db, with_checklist=True)
        appt, _, _ = _book(ctx, hours_from_now=24)
        tasks = client.get(f"/appointments/{appt['id']}/admin-tasks", headers=ctx["admin_h"]).json()
        admin_task = next(t for t in tasks if t["side"] == "admin")

        r = client.put(f"/appointments/admin-tasks/{admin_task['id']}", headers=ctx["admin_h"],
                       json={"is_done": True, "actor_name": "實習心理師（魏啓倫）"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_done"] is True
        assert body["done_at"] is not None
        assert body["done_by_name"] == "實習心理師（魏啓倫）"

    def test_therapist_cannot_tick_admin_side(self, db, http_db):
        ctx = _seed(db, with_checklist=True)
        appt, _, _ = _book(ctx, hours_from_now=24)
        tasks = client.get(f"/appointments/{appt['id']}/admin-tasks", headers=ctx["admin_h"]).json()
        admin_task = next(t for t in tasks if t["side"] == "admin")
        r = client.put(f"/appointments/admin-tasks/{admin_task['id']}", headers=ctx["t_h"],
                       json={"is_done": True})
        assert r.status_code == 403

    def test_no_checklist_no_tasks(self, db, http_db):
        ctx = _seed(db, with_checklist=False)
        appt, _, _ = _book(ctx, hours_from_now=24)
        r = client.get(f"/appointments/{appt['id']}/admin-tasks", headers=ctx["admin_h"])
        assert r.json() == []


class TestVenueRental:
    def _payload(self, ctx, hours, **kw):
        start = datetime.now(timezone.utc) + timedelta(hours=hours)
        base = {
            "room_id": ctx["room"].id,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "renter_name": "蛹之生心理諮商所",
            "renter_kind": "institution",
            "institution_id": ctx["inst"].id,
            "amount": 1200,
        }
        base.update(kw)
        return base

    def test_create_and_number(self, db, http_db):
        ctx = _seed(db)
        r = client.post("/venues", headers=ctx["admin_h"], json=self._payload(ctx, 72))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["rental_no"].startswith("V")
        assert body["payer"] == "institution", "機構借用 → 機構應收"
        assert body["attendance"] == "pending"

    def test_conflicts_with_a_normal_appointment(self, db, http_db):
        """場地租借跟一般預約共用實體診間，衝突要跨表看見。"""
        ctx = _seed(db)
        _, start, _ = _book(ctx, hours_from_now=96)
        r = client.post("/venues", headers=ctx["admin_h"], json={
            "room_id": ctx["room"].id,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
            "renter_name": "某單位", "renter_kind": "institution",
            "institution_id": ctx["inst"].id, "amount": 1000,
        })
        assert r.status_code == 409, r.text
        assert "預約" in r.json()["detail"]

    def test_appointment_blocked_by_existing_rental(self, db, http_db):
        """反方向也要擋：已經租出去的診間不能再排一般預約。"""
        ctx = _seed(db)
        start = datetime.now(timezone.utc) + timedelta(hours=120)
        r = client.post("/venues", headers=ctx["admin_h"], json={
            "room_id": ctx["room2"].id,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=3)).isoformat(),
            "renter_name": "鉅微管理顧問", "renter_kind": "institution",
            "institution_id": ctx["inst"].id, "amount": 1500,
        })
        assert r.status_code == 201, r.text

        r2 = client.post("/appointments", headers=ctx["admin_h"], json={
            "case_id": ctx["case"].id, "room_id": ctx["room2"].id, "session_type": "in_person",
            "start_time": (start + timedelta(hours=1)).isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "plan_id": ctx["plan"].id,
        })
        assert r2.status_code == 409, r2.text
        assert "場地租借" in r2.json()["detail"]

    def test_supervision_mode_a_forces_zero_venue_fee(self, db, http_db):
        """模式 A：櫃台代收督導費並開收據，場地費自動 $0（不重複收）。"""
        ctx = _seed(db)
        r = client.post("/venues", headers=ctx["admin_h"], json=self._payload(
            ctx, 150, renter_kind="private", institution_id=None,
            renter_therapist_id=ctx["therapist"].id, supervision_fee_mode="A", amount=1200,
        ))
        assert r.status_code == 201, r.text
        assert r.json()["amount"] == 0.0
        assert r.json()["payer"] == "renter"

    def test_supervision_mode_b_charges_therapist(self, db, http_db):
        """模式 B：心理師自收督導費，場地費照收、從酬勞扣回。"""
        ctx = _seed(db)
        r = client.post("/venues", headers=ctx["admin_h"], json=self._payload(
            ctx, 170, renter_kind="private", institution_id=None,
            renter_therapist_id=ctx["therapist"].id, supervision_fee_mode="B", amount=1200,
        ))
        assert r.status_code == 201, r.text
        assert r.json()["amount"] == 1200.0
        assert r.json()["payer"] == "therapist"

    def test_no_show_flips_payer_to_renter(self, db, http_db):
        ctx = _seed(db)
        rental = client.post("/venues", headers=ctx["admin_h"], json=self._payload(ctx, 200)).json()
        assert rental["payer"] == "institution"
        r = client.put(f"/venues/{rental['id']}/attendance", headers=ctx["admin_h"],
                       json={"attendance": "no_show"})
        assert r.status_code == 200, r.text
        assert r.json()["payer"] == "renter", "未到 → 付款方改為借用人自付（場地已被佔住）"


class TestHallBooking:
    def _payload(self, ctx, days, **kw):
        start = datetime.now(timezone.utc) + timedelta(days=days)
        base = {
            "title": "親職教養講座",
            "event_start": start.isoformat(),
            "event_end": (start + timedelta(hours=3)).isoformat(),
            "setup_start": (start - timedelta(hours=1)).isoformat(),
            "setup_end": start.isoformat(),
            "lecturer_kind": "internal",
            "lecturer_therapist_id": ctx["therapist"].id,
            "lecturer_fee": 6000,
            "fee_to_clinic_account": True,
            "borrower": "臺南市政府社會局",
            "attendee_count": 40,
        }
        base.update(kw)
        return base

    def test_create_with_setup_and_event_ranges(self, db, http_db):
        ctx = _seed(db)
        r = client.post("/venues/hall", headers=ctx["admin_h"], json=self._payload(ctx, 10))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["setup_start"] is not None and body["event_start"] is not None
        assert body["lecturer_name"] == ctx["therapist"].name
        assert body["status"] == "scheduled"

    def test_external_lecturer_requires_name(self, db, http_db):
        ctx = _seed(db)
        r = client.post("/venues/hall", headers=ctx["admin_h"], json=self._payload(
            ctx, 12, lecturer_kind="external", lecturer_therapist_id=None, lecturer_name=None))
        assert r.status_code == 400

    def test_overlapping_event_rejected(self, db, http_db):
        ctx = _seed(db)
        p = self._payload(ctx, 14)
        assert client.post("/venues/hall", headers=ctx["admin_h"], json=p).status_code == 201
        r = client.post("/venues/hall", headers=ctx["admin_h"], json=p)
        assert r.status_code == 409, r.text

    def test_setup_must_end_before_event_starts(self, db, http_db):
        ctx = _seed(db)
        start = datetime.now(timezone.utc) + timedelta(days=16)
        r = client.post("/venues/hall", headers=ctx["admin_h"], json=self._payload(
            ctx, 16, setup_start=start.isoformat(),
            setup_end=(start + timedelta(hours=2)).isoformat()))
        assert r.status_code == 400

    def test_status_transitions(self, db, http_db):
        ctx = _seed(db)
        h = client.post("/venues/hall", headers=ctx["admin_h"], json=self._payload(ctx, 18)).json()
        r = client.put(f"/venues/hall/{h['id']}/status", headers=ctx["admin_h"],
                       json={"status": "executed"})
        assert r.status_code == 200 and r.json()["status"] == "executed"
