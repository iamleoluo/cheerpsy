"""媒合管理子系統：派案→承接/婉拒→轉預約→初診有到/未到→轉為正式個案。
見 document_reference/cheerpsy_v7_spec_extracted.md「媒合管理」。
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room
from app.models.user import User
from app.referral.models.batch import ReferralBatch, ReferralBatchMember
from app.referral.models.referral import Referral

client = TestClient(app)


def _admin(db, code="A980"):
    admin = User(email=f"ref_admin_{code}@test.local", password_hash=hash_password("x"), name="媒合測試管理員", role="admin", user_code=code)
    db.add(admin)
    db.flush()
    return admin


def _therapist(db, code, name="媒合測試心理師"):
    t = User(email=f"ref_t_{code}@test.local", password_hash=hash_password("x"), name=name, role="therapist", user_code=code)
    db.add(t)
    db.flush()
    return t


def _token(user):
    return create_access_token({"sub": str(user.id), "role": user.role, "name": user.name})


def _headers(user):
    return {"Authorization": f"Bearer {_token(user)}"}


class TestCreateAndAssign:
    def test_create_referral_generates_code(self, db, http_db):
        admin = _admin(db)
        r = client.post("/referrals", headers=_headers(admin), json={"name": "王小明", "age": 28, "gender": "male", "phone": "0912345678", "mode": "in_person", "source": "自行來電"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "new"
        assert len(body["referral_code"]) == 9  # YYMMDD + 3碼

    def test_assign_up_to_three_therapists(self, db, http_db):
        admin = _admin(db, "A981")
        t1 = _therapist(db, "T981a")
        t2 = _therapist(db, "T981b")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "陳小華"})
        rid = r.json()["id"]

        r2 = client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id, t2.id]})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "matching"
        assert len(body["batches"]) == 1
        assert len(body["batches"][0]["members"]) == 2

    def test_assign_more_than_three_rejected(self, db, http_db):
        admin = _admin(db, "A982")
        ids = [_therapist(db, f"T982{i}").id for i in range(4)]
        r = client.post("/referrals", headers=_headers(admin), json={"name": "測試"})
        rid = r.json()["id"]
        r2 = client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": ids})
        assert r2.status_code == 400


class TestAcceptDeclineRelease:
    def test_accept_supersedes_others_and_flips_status(self, db, http_db):
        admin = _admin(db, "A983")
        t1 = _therapist(db, "T983a")
        t2 = _therapist(db, "T983b")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "林小美"})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id, t2.id]})

        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = next(m for m in detail["batches"][0]["members"] if m["therapist_id"] == t1.id)
        member2 = next(m for m in detail["batches"][0]["members"] if m["therapist_id"] == t2.id)

        slot = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r2 = client.put(f"/referrals/pool/{member1['id']}/accept", headers=_headers(t1), json={"slots": [slot]})
        assert r2.status_code == 200, r2.text
        assert r2.json()["reply_status"] == "accepted"

        detail2 = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        assert detail2["status"] == "accepted"
        assert detail2["accepted_therapist_id"] == t1.id
        member2_after = next(m for m in detail2["batches"][0]["members"] if m["id"] == member2["id"])
        assert member2_after["reply_status"] == "superseded"

    def test_decline_with_bad_reason_rejected(self, db, http_db):
        admin = _admin(db, "A984")
        t1 = _therapist(db, "T984a")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "測試"})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = detail["batches"][0]["members"][0]

        r2 = client.put(f"/referrals/pool/{member1['id']}/decline", headers=_headers(t1), json={"reason": "not_a_real_reason"})
        assert r2.status_code == 400

    def test_all_decline_marks_unmatched(self, db, http_db):
        admin = _admin(db, "A985")
        t1 = _therapist(db, "T985a")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "測試"})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = detail["batches"][0]["members"][0]

        r2 = client.put(f"/referrals/pool/{member1['id']}/decline", headers=_headers(t1), json={"reason": "not_specialty"})
        assert r2.status_code == 200

        detail2 = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        assert detail2["status"] == "unmatched"

        # 可重新派案
        t2 = _therapist(db, "T985b")
        r3 = client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t2.id]})
        assert r3.status_code == 200
        assert r3.json()["status"] == "matching"
        assert len(r3.json()["batches"]) == 2

    def test_release_after_accept_reopens_for_reassign(self, db, http_db):
        admin = _admin(db, "A986")
        t1 = _therapist(db, "T986a")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "測試"})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = detail["batches"][0]["members"][0]
        client.put(f"/referrals/pool/{member1['id']}/accept", headers=_headers(t1), json={"slots": [datetime.now(timezone.utc).isoformat()]})

        r2 = client.put(f"/referrals/pool/{member1['id']}/release", headers=_headers(t1))
        assert r2.status_code == 200
        assert r2.json()["reply_status"] == "released"

        detail2 = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        assert detail2["status"] == "unmatched"
        assert detail2["accepted_therapist_id"] is None


class TestTimeout:
    def test_batch_older_than_return_days_auto_expires(self, db, http_db):
        admin = _admin(db, "A987")
        t1 = _therapist(db, "T987a")
        referral = Referral(referral_code="TESTTIMEOUT1", name="逾時測試", status="matching", created_by=admin.id)
        db.add(referral)
        db.flush()
        batch = ReferralBatch(referral_id=referral.id, batch_seq=1, sent_at=datetime.now(timezone.utc) - timedelta(days=4))
        db.add(batch)
        db.flush()
        db.add(ReferralBatchMember(batch_id=batch.id, therapist_id=t1.id))
        db.commit()

        r = client.get("/referrals", headers=_headers(admin))
        assert r.status_code == 200
        body = next(x for x in r.json() if x["id"] == referral.id)
        assert body["status"] == "unmatched"
        assert body["batches"][0]["members"][0]["reply_status"] == "expired"


class TestConvertAndArrival:
    def _accepted_referral(self, db, admin, therapist):
        r = client.post("/referrals", headers=_headers(admin), json={
            "name": "轉預約測試個案", "age": 30, "gender": "female", "phone": "0900000000", "mode": "in_person",
        })
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [therapist.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = detail["batches"][0]["members"][0]
        client.put(f"/referrals/pool/{member1['id']}/accept", headers=_headers(therapist), json={"slots": [datetime.now(timezone.utc).isoformat()]})
        return rid

    def test_convert_creates_case_and_appointment(self, db, http_db):
        admin = _admin(db, "A988")
        therapist = _therapist(db, "T988a")
        room = Room(name="ref room", floor=1, room_code="REF-1A", use_type="general", size="normal")
        db.add(room)
        db.flush()
        rid = self._accepted_referral(db, admin, therapist)

        start = datetime.now(timezone.utc) + timedelta(days=1)
        end = start + timedelta(hours=1)
        r = client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "booked"
        assert body["converted_case_id"] is not None
        assert body["appointment_id"] is not None

        case = db.query(Case).filter(Case.id == body["converted_case_id"]).first()
        assert case.name == "轉預約測試個案"
        assert case.status == "initial"
        assert case.therapist_id == therapist.id
        appt = db.query(Appointment).filter(Appointment.id == body["appointment_id"]).first()
        assert appt.case_id == case.id

    def test_arrived_activates_case_and_checks_in_appointment(self, db, http_db):
        admin = _admin(db, "A989")
        therapist = _therapist(db, "T989a")
        room = Room(name="ref room2", floor=1, room_code="REF-1B", use_type="general", size="normal")
        db.add(room)
        db.flush()
        rid = self._accepted_referral(db, admin, therapist)
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = start + timedelta(hours=1)
        client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })

        r = client.put(f"/referrals/{rid}/arrived", headers=_headers(admin), json={
            "national_id": "A123456789", "birth_date": "1995-01-01", "phone": "0911111111",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "converted"

        case = db.query(Case).filter(Case.id == body["converted_case_id"]).first()
        assert case.status == "ongoing"
        assert case.case_number is not None
        appt = db.query(Appointment).filter(Appointment.id == body["appointment_id"]).first()
        assert appt.check_in_status == "arrived"

        # 已轉個案 → 離開媒合列表（active_only），出現在媒合結案表
        active = client.get("/referrals", headers=_headers(admin)).json()
        assert rid not in [x["id"] for x in active]
        closed = client.get("/referrals?active_only=false", headers=_headers(admin)).json()
        assert rid in [x["id"] for x in closed]

    def test_no_show_reassign_clears_accepted_therapist(self, db, http_db):
        admin = _admin(db, "A990")
        therapist = _therapist(db, "T990a")
        room = Room(name="ref room3", floor=1, room_code="REF-1C", use_type="general", size="normal")
        db.add(room)
        db.flush()
        rid = self._accepted_referral(db, admin, therapist)
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = start + timedelta(hours=1)
        client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })

        r = client.put(f"/referrals/{rid}/no-show", headers=_headers(admin), json={"reason": "unreachable", "next_action": "reassign"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "unmatched"
        assert body["accepted_therapist_id"] is None

        appt = db.query(Appointment).filter(Appointment.id == body["appointment_id"]).first()
        assert appt.check_in_status == "no_show"

        # 個案本身還在，重新派案給另一位心理師後可再次轉預約（重用同一個案）
        t2 = _therapist(db, "T990b")
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t2.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member2 = detail["batches"][-1]["members"][0]
        client.put(f"/referrals/pool/{member2['id']}/accept", headers=_headers(t2), json={"slots": [datetime.now(timezone.utc).isoformat()]})

        start2 = datetime.now(timezone.utc) + timedelta(days=2)
        end2 = start2 + timedelta(hours=1)
        r2 = client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person", "start_time": start2.isoformat(), "end_time": end2.isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })
        assert r2.status_code == 200, r2.text
        case_id_1 = body["converted_case_id"]
        assert r2.json()["converted_case_id"] == case_id_1  # 重用同一筆個案，不重建
        case = db.query(Case).filter(Case.id == case_id_1).first()
        assert case.therapist_id == t2.id


class TestCancel:
    def test_cancel_active_referral(self, db, http_db):
        admin = _admin(db, "A991")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "取消測試"})
        rid = r.json()["id"]
        r2 = client.put(f"/referrals/{rid}/cancel", headers=_headers(admin), json={"reason": "個案自行取消"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "cancelled"

    def test_cancel_already_converted_rejected(self, db, http_db):
        admin = _admin(db, "A992")
        therapist = _therapist(db, "T992a")
        room = Room(name="ref room4", floor=1, room_code="REF-1D", use_type="general", size="normal")
        db.add(room)
        db.flush()
        r = client.post("/referrals", headers=_headers(admin), json={"name": "測試"})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [therapist.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member1 = detail["batches"][0]["members"][0]
        client.put(f"/referrals/pool/{member1['id']}/accept", headers=_headers(therapist), json={"slots": [datetime.now(timezone.utc).isoformat()]})
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = start + timedelta(hours=1)
        client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })
        client.put(f"/referrals/{rid}/arrived", headers=_headers(admin), json={
            "national_id": "A223456789", "birth_date": "1995-01-01", "phone": "0911111111",
        })
        r2 = client.put(f"/referrals/{rid}/cancel", headers=_headers(admin), json={"reason": "測試"})
        assert r2.status_code == 400


class TestPoolViews:
    def test_pending_accepted_history_tabs(self, db, http_db):
        admin = _admin(db, "A993")
        t1 = _therapist(db, "T993a")
        t2 = _therapist(db, "T993b")
        r = client.post("/referrals", headers=_headers(admin), json={"name": "小美", "source": "親友介紹", "designated_therapist_id": t1.id})
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [t1.id, t2.id]})

        pending1 = client.get("/referrals/pool/pending", headers=_headers(t1)).json()
        assert len(pending1) == 1
        assert pending1[0]["is_dual_relationship_risk"] is True
        assert pending1[0]["designated_label"].startswith("是")
        assert pending1[0]["other_pending_count"] == 1

        pending2 = client.get("/referrals/pool/pending", headers=_headers(t2)).json()
        assert pending2[0]["designated_label"] == "指定心理師無法安排"

        member1_id = pending1[0]["member_id"]
        client.put(f"/referrals/pool/{member1_id}/accept", headers=_headers(t1), json={"slots": [datetime.now(timezone.utc).isoformat()]})

        accepted = client.get("/referrals/pool/accepted", headers=_headers(t1)).json()
        assert len(accepted) == 1

        history2 = client.get("/referrals/pool/history", headers=_headers(t2)).json()
        assert len(history2) == 1
        assert history2[0]["reply_status"] == "superseded"
