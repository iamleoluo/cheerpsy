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
from app.utils.tz import to_local_date
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


class TestFirstVisitGate:
    """初診報到搬到診間日曆（11 §5.9）。

    初診預約就是一筆普通的 appointments 列，本來就會出現在診間日曆上。在補這道
    閘門之前，行政直接在日曆按「已到」是**走得通的**：預約變 arrived、場次照常
    建立、畫面一切正常——但媒合案永遠卡在 booked，個案永遠停在 initial，也就
    永遠拿不到病歷號。那條會把資料走壞的路，正好是行政最自然會走的那條。
    """

    def _booked(self, db, admin, therapist, room_code, start=None):
        r = client.post("/referrals", headers=_headers(admin), json={
            "name": "初診閘門測試", "age": 31, "gender": "female", "phone": "0900111222", "mode": "in_person",
        })
        rid = r.json()["id"]
        client.put(f"/referrals/{rid}/assign", headers=_headers(admin), json={"therapist_ids": [therapist.id]})
        detail = client.get(f"/referrals/{rid}", headers=_headers(admin)).json()
        member = detail["batches"][0]["members"][0]
        client.put(f"/referrals/pool/{member['id']}/accept", headers=_headers(therapist),
                   json={"slots": [datetime.now(timezone.utc).isoformat()]})

        room = Room(name=f"gate {room_code}", floor=1, room_code=room_code, use_type="general", size="normal")
        db.add(room)
        db.flush()
        start = start or (datetime.now(timezone.utc) - timedelta(hours=1))
        body = client.put(f"/referrals/{rid}/convert", headers=_headers(admin), json={
            "room_id": room.id, "session_type": "in_person",
            "start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        }).json()
        return rid, body["appointment_id"], body["converted_case_id"], room

    def test_plain_check_in_on_first_visit_is_refused(self, db, http_db):
        admin = _admin(db, "A9A1")
        therapist = _therapist(db, "T9A1")
        rid, appt_id, case_id, _ = self._booked(db, admin, therapist, "GATE-1A")

        r = client.put(f"/appointments/{appt_id}/check-in", headers=_headers(admin), json={"status": "arrived"})
        assert r.status_code == 400, r.text
        assert "初診" in r.json()["detail"]

        # 而且什麼都沒被改到——這才是重點，不是「有沒有回錯誤」
        db.expire_all()
        assert db.query(Appointment).filter(Appointment.id == appt_id).first().check_in_status == "pending"
        assert db.query(Referral).filter(Referral.id == rid).first().status == "booked"
        case = db.query(Case).filter(Case.id == case_id).first()
        assert case.status == "initial"
        assert case.case_number is None

    def test_plain_no_show_on_first_visit_is_refused(self, db, http_db):
        """未到這半邊不補，媒合案一樣會斷在半路——初診未到帶著轉預約／派案／
        結案的分流，那是普通 no_show 不會做的事。"""
        admin = _admin(db, "A9A2")
        therapist = _therapist(db, "T9A2")
        rid, appt_id, _, _ = self._booked(db, admin, therapist, "GATE-1B")

        r = client.put(f"/appointments/{appt_id}/check-in", headers=_headers(admin),
                       json={"status": "no_show", "no_show_reason": "case_leave"})
        assert r.status_code == 400, r.text
        db.expire_all()
        assert db.query(Appointment).filter(Appointment.id == appt_id).first().check_in_status == "pending"
        assert db.query(Referral).filter(Referral.id == rid).first().status == "booked"

    def test_room_calendar_marks_the_cell_as_first_visit(self, db, http_db):
        admin = _admin(db, "A9A3")
        therapist = _therapist(db, "T9A3")
        rid, appt_id, _, _ = self._booked(db, admin, therapist, "GATE-1C")

        day = to_local_date(datetime.now(timezone.utc) - timedelta(hours=1))
        cells = client.get(f"/room-calendar?q={day}", headers=_headers(admin)).json()["cells"]
        cell = next(c for c in cells if c["appointment_id"] == appt_id)
        assert cell["first_visit"] is not None
        assert cell["first_visit"]["referral_id"] == rid
        # 需求表有填電話，會跟著帶進個案 → 只缺身分證與出生日期
        assert cell["first_visit"]["missing_fields"] == ["national_id", "birth_date"]

    def test_missing_fields_matches_what_activation_actually_demands(self, db, http_db):
        """表單問的東西，必須**剛好**是 activate_case 會擋的東西。

        第一版只回了 needs_national_id，於是表單把出生日期標成「選填」——
        櫃檯填完按下去才被打回「轉正式前需填寫：出生日期」。兩份清單各自
        演化就會這樣分岔，所以這裡拿真實回應去撞真實閘門。
        """
        admin = _admin(db, "A9A5")
        therapist = _therapist(db, "T9A5")
        rid, appt_id, case_id, _ = self._booked(db, admin, therapist, "GATE-1E")

        day = to_local_date(datetime.now(timezone.utc) - timedelta(hours=1))
        cells = client.get(f"/room-calendar?q={day}", headers=_headers(admin)).json()["cells"]
        missing = next(c for c in cells if c["appointment_id"] == appt_id)["first_visit"]["missing_fields"]

        # 只補「沒被列為缺」的欄位，報到應該還是會被閘門擋下來
        partial = {f: v for f, v in
                   {"national_id": "A123456781", "birth_date": "1990-02-02", "phone": "0933444555"}.items()
                   if f not in missing}
        r = client.put(f"/referrals/{rid}/arrived", headers=_headers(admin), json=partial)
        assert r.status_code == 400, "缺的欄位沒補卻過了，代表 missing_fields 少報"
        assert "轉正式前需填寫" in r.json()["detail"]

        # 把 missing_fields 說缺的都補上，就該一次過——不能有「多要的」欄位
        full = {f: v for f, v in
                {"national_id": "A123456781", "birth_date": "1990-02-02", "phone": "0933444555"}.items()
                if f in missing}
        r2 = client.put(f"/referrals/{rid}/arrived", headers=_headers(admin), json=full)
        assert r2.status_code == 200, f"補齊 missing_fields 仍被擋，代表少報：{r2.text}"
        db.expire_all()
        assert db.query(Case).filter(Case.id == case_id).first().case_number is not None

    def test_referral_flow_still_works_and_then_gate_lifts(self, db, http_db):
        """閘門只擋「還沒報到的初診」。走完初診流程後，同一個個案的下一次
        預約要能正常報到，否則等於把人鎖在外面。"""
        admin = _admin(db, "A9A4")
        therapist = _therapist(db, "T9A4")
        rid, appt_id, case_id, room = self._booked(db, admin, therapist, "GATE-1D")

        r = client.put(f"/referrals/{rid}/arrived", headers=_headers(admin),
                       json={"national_id": "A123456780", "birth_date": "1994-03-03", "phone": "0922333444"})
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.query(Appointment).filter(Appointment.id == appt_id).first().check_in_status == "arrived"
        case = db.query(Case).filter(Case.id == case_id).first()
        assert case.status == "ongoing"
        assert case.case_number is not None

        # 第二次晤談：普通預約、普通報到，不該再被擋
        # 初診佔的是 now-1h~now，第二次要錯開，否則撞的是診間衝突不是閘門
        start2 = datetime.now(timezone.utc) + timedelta(hours=2)
        appt2 = client.post("/appointments", headers=_headers(admin), json={
            "case_id": case_id, "room_id": room.id, "session_type": "in_person",
            "start_time": start2.isoformat(), "end_time": (start2 + timedelta(hours=1)).isoformat(),
            "amount": 1600, "funding_source": "self_pay",
        })
        assert appt2.status_code == 201, appt2.text
        r2 = client.put(f"/appointments/{appt2.json()['id']}/check-in", headers=_headers(admin), json={"status": "arrived"})
        assert r2.status_code == 200, r2.text
