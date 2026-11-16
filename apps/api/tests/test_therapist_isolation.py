"""心理師之間的隔離：心理師只能看到自己的個案資料；staff／admin 權限不變。"""

import json

import pytest

from app.models.reminder_log import ReminderLog
from app.models.referral import (
    ReferralDispatch,
    ReferralDispatchTarget,
    ReferralRequest,
)

SECRET_NAME = "陳大文"
SECRET_PHONE = "0988-111-222"
SECRET_COMPLAINT = "家暴創傷"


@pytest.fixture()
def world(make_user, make_case, make_appt, room):
    """甲、乙兩位心理師，各有一個案與一場在同一診間的預約。"""
    a = make_user("therapist", name="甲心理師")
    b = make_user("therapist", name="乙心理師")
    staff = make_user("staff")
    admin = make_user("admin")
    case_a = make_case(a, "甲的個案")
    case_b = make_case(b, SECRET_NAME, phone=SECRET_PHONE, chief_complaint=SECRET_COMPLAINT)
    appt_a = make_appt(case_a, a, room)
    appt_b = make_appt(case_b, b, room)
    return dict(a=a, b=b, staff=staff, admin=admin, case_a=case_a, case_b=case_b,
                appt_a=appt_a, appt_b=appt_b, room=room)


def _leaks(resp) -> bool:
    text = json.dumps(resp.json(), ensure_ascii=False)
    return any(s in text for s in (SECRET_NAME, SECRET_PHONE, SECRET_COMPLAINT))


# ---- /appointments --------------------------------------------------------
def test_therapist_list_only_own(client, auth, world):
    r = client.get("/appointments", headers=auth(world["a"]))
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert ids == {world["appt_a"].id}


def test_room_view_masks_other_therapist(client, auth, world):
    r = client.get(f"/appointments?room_id={world['room'].id}", headers=auth(world["a"]))
    assert r.status_code == 200
    rows = {x["id"]: x for x in r.json()}
    assert set(rows) == {world["appt_a"].id, world["appt_b"].id}

    mine = rows[world["appt_a"].id]
    assert mine["case_name"] == "甲的個案" and mine["occupied_only"] is False

    other = rows[world["appt_b"].id]
    assert other["occupied_only"] is True
    assert other["therapist_name"] == "乙心理師"
    assert other["case_id"] == 0
    assert other["case_name"] is None and other["couple_case_id"] is None
    assert other["amount"] == 0 and other["appointment_number"] == ""
    assert other["video_link"] is None and other["outreach_location"] is None
    assert other["quota_id"] is None and other["funding_source"] == "self_pay"
    assert not _leaks(r)


def test_room_view_hides_other_cancelled_and_no_show(client, auth, world, make_appt):
    make_appt(world["case_b"], world["b"], world["room"], status="cancelled")
    make_appt(world["case_b"], world["b"], world["room"], status="no_show")
    r = client.get(f"/appointments?room_id={world['room'].id}", headers=auth(world["a"]))
    assert {x["id"] for x in r.json()} == {world["appt_a"].id, world["appt_b"].id}


def test_case_id_filter_cannot_reach_other_therapist(client, auth, world):
    r = client.get(
        f"/appointments?room_id={world['room'].id}&case_id={world['case_b'].id}",
        headers=auth(world["a"]),
    )
    assert r.json() == []
    r = client.get(f"/appointments?case_id={world['case_b'].id}", headers=auth(world["a"]))
    assert r.json() == []


def test_get_other_appointment_403(client, auth, world):
    r = client.get(f"/appointments/{world['appt_b'].id}", headers=auth(world["a"]))
    assert r.status_code == 403


def test_staff_sees_full_room_view(client, auth, world):
    r = client.get(f"/appointments?room_id={world['room'].id}", headers=auth(world["staff"]))
    rows = {x["id"]: x for x in r.json()}
    assert rows[world["appt_b"].id]["case_name"] == SECRET_NAME
    assert rows[world["appt_b"].id]["occupied_only"] is False


# ---- /cases ---------------------------------------------------------------
def test_cases_list_and_get(client, auth, world):
    r = client.get("/cases", headers=auth(world["a"]))
    assert [c["id"] for c in r.json()] == [world["case_a"].id]
    assert client.get(f"/cases/{world['case_b'].id}", headers=auth(world["a"])).status_code == 403
    r = client.get(f"/cases?q={SECRET_NAME}", headers=auth(world["a"]))
    assert r.json() == []
    r = client.get(f"/cases?therapist_id={world['b'].id}", headers=auth(world["a"]))
    assert all(c["therapist_id"] == world["a"].id for c in r.json())


def test_staff_sees_all_cases(client, auth, world):
    r = client.get("/cases", headers=auth(world["staff"]))
    assert {c["id"] for c in r.json()} == {world["case_a"].id, world["case_b"].id}


# ---- /referrals -----------------------------------------------------------
@pytest.fixture()
def referral(db, world):
    r = ReferralRequest(dispatch_code="261116001", name=SECRET_NAME, phone=SECRET_PHONE,
                        chief_complaint=SECRET_COMPLAINT, age=30, consultation_mode="individual",
                        status="matching")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1)
    db.add(d)
    db.flush()
    t = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=world["b"].id, status="declined",
                               decline_reason="other", decline_note="私人備註")
    db.add(t)
    db.commit()
    return r


def test_referral_list_forbidden_for_therapist(client, auth, world, referral):
    assert client.get("/referrals", headers=auth(world["a"])).status_code == 403
    assert client.get("/referrals?closed=true", headers=auth(world["a"])).status_code == 403


def test_referral_dispatches_forbidden_for_therapist(client, auth, world, referral):
    r = client.get(f"/referrals/{referral.id}/dispatches", headers=auth(world["a"]))
    assert r.status_code == 403


def test_staff_and_admin_can_still_list_referrals(client, auth, world, referral):
    for who in ("staff", "admin"):
        r = client.get("/referrals", headers=auth(world[who]))
        assert r.status_code == 200 and r.json()[0]["name"] == SECRET_NAME
        assert client.get(f"/referrals/{referral.id}/dispatches", headers=auth(world[who])).status_code == 200


@pytest.mark.parametrize("status,visible", [
    ("pending", True), ("accepted", True),
    ("declined", False), ("taken", False), ("expired", False), ("released", False),
])
def test_invite_masked_unless_pending_or_accepted(client, auth, db, world, referral, status, visible):
    t = db.query(ReferralDispatchTarget).first()
    t.therapist_id = world["a"].id
    t.status = status
    db.commit()
    tab = {"pending": "pending", "accepted": "accepted"}.get(status, "closed")
    r = client.get(f"/referrals/invites?tab={tab}", headers=auth(world["a"]))
    assert r.status_code == 200
    (inv,) = r.json()
    assert inv["dispatch_code"] == referral.dispatch_code  # 派案碼永遠保留
    if visible:
        assert inv["name"] == SECRET_NAME and inv["chief_complaint"] == SECRET_COMPLAINT
    else:
        assert not _leaks(r)
        assert inv["age"] is None and inv["gender"] is None and inv["plan_name"] is None


def test_invites_never_contain_phone(client, auth, db, world, referral):
    t = db.query(ReferralDispatchTarget).first()
    t.therapist_id = world["a"].id
    t.status = "pending"
    db.commit()
    r = client.get("/referrals/invites", headers=auth(world["a"]))
    assert SECRET_PHONE not in json.dumps(r.json(), ensure_ascii=False)


# ---- /reports -------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/reports/intake?year=2026&month=11",
    "/reports/intake/export?year=2026&month=11",
    "/reports/therapist-load?year=2026&month=11",
])
def test_reports_forbidden_for_therapist(client, auth, world, path):
    assert client.get(path, headers=auth(world["a"])).status_code == 403


@pytest.mark.parametrize("path", [
    "/reports/intake?year=2026&month=11",
    "/reports/therapist-load?year=2026&month=11",
])
def test_reports_still_open_to_staff_and_admin(client, auth, world, path):
    for who in ("staff", "admin"):
        assert client.get(path, headers=auth(world[who])).status_code == 200


# ---- /reminders -----------------------------------------------------------
def test_reminder_logs_scoped(client, auth, db, world):
    db.add(ReminderLog(appointment_id=world["appt_b"].id, contact_result="confirmed",
                       notes="個案說最近很不好", contacted_by=world["staff"].id))
    db.commit()
    # 乙看自己的 OK，甲看乙的 → 404
    assert client.get(f"/reminders/logs/{world['appt_b'].id}", headers=auth(world["b"])).status_code == 200
    r = client.get(f"/reminders/logs/{world['appt_b'].id}", headers=auth(world["a"]))
    assert r.status_code == 404 and "個案說" not in r.text
    assert client.get(f"/reminders/logs/{world['appt_b'].id}", headers=auth(world["staff"])).status_code == 200


def test_reminder_create_scoped(client, auth, world):
    body = {"appointment_id": world["appt_b"].id, "contact_result": "confirmed"}
    assert client.post("/reminders", json=body, headers=auth(world["a"])).status_code == 404
    assert client.post("/reminders", json=body, headers=auth(world["b"])).status_code == 201
    assert client.post("/reminders", json=body, headers=auth(world["staff"])).status_code == 201
    # 不存在的預約與「別人的預約」回應相同，無法探測
    ghost = client.post("/reminders", json={**body, "appointment_id": 99999}, headers=auth(world["a"]))
    assert ghost.status_code == 404


# ---- /cases/{id}/quotas ---------------------------------------------------
def test_case_quotas_scoped(client, auth, world):
    cid = world["case_b"].id
    for path in (f"/cases/{cid}/quotas", f"/cases/{cid}/quotas/available"):
        assert client.get(path, headers=auth(world["a"])).status_code == 404
        assert client.get(path, headers=auth(world["b"])).status_code == 200
        assert client.get(path, headers=auth(world["staff"])).status_code == 200
    assert client.get("/quotas", headers=auth(world["a"])).status_code == 200


# ---- /claim-batches -------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/claim-batches",
    "/claim-batches/eligible-cases",
    "/claim-batches/eligible-institutions",
    "/claim-batches/unassigned/records",
    "/claim-batches/1",
    "/claim-batches/1/records",
    "/claim-batches/1/plans",
])
def test_claim_batch_reads_forbidden_for_therapist(client, auth, world, path):
    assert client.get(path, headers=auth(world["a"])).status_code == 403


def test_claim_batch_reads_open_to_staff(client, auth, world):
    for who in ("staff", "admin"):
        assert client.get("/claim-batches", headers=auth(world[who])).status_code == 200
    # 心理師自己的核銷待辦不受影響
    assert client.get("/claim-batches/my/pending-docs", headers=auth(world["a"])).status_code == 200


# ---- /auth/therapists -----------------------------------------------------
def test_therapist_list_hides_colleague_pay(client, auth, db, world):
    world["a"].commission_rate = 0.6
    world["a"].base_price = 1800
    world["b"].commission_rate = 0.7
    world["b"].base_price = 2200
    db.commit()
    rows = {t["id"]: t for t in client.get("/auth/therapists", headers=auth(world["a"])).json()}
    assert rows[world["a"].id]["base_price"] == 1800
    assert rows[world["a"].id]["commission_rate"] == 0.6
    assert rows[world["b"].id]["base_price"] is None
    assert rows[world["b"].id]["commission_rate"] is None
    assert rows[world["b"].id]["email"] == ""
    assert rows[world["b"].id]["name"] == "乙心理師"  # 姓名仍可見（選擇心理師用）


def test_staff_still_sees_pay_in_therapist_list(client, auth, db, world):
    world["b"].base_price = 2200
    db.commit()
    rows = {t["id"]: t for t in client.get("/auth/therapists", headers=auth(world["staff"])).json()}
    assert rows[world["b"].id]["base_price"] == 2200


# ---- 伴侶案成員 -----------------------------------------------------------
def test_couple_members_filtered_for_therapist(client, auth, db, world, make_case):
    from app.models.couple_member import CoupleMember

    couple = make_case(world["a"], "甲的伴侶案", case_type="couple")
    mine = make_case(world["a"], "我的成員")
    theirs = make_case(world["b"], "別人的成員")
    db.add_all([CoupleMember(couple_case_id=couple.id, member_case_id=mine.id),
                CoupleMember(couple_case_id=couple.id, member_case_id=theirs.id)])
    db.commit()
    r = client.get(f"/cases/{couple.id}", headers=auth(world["a"]))
    assert [m["name"] for m in r.json()["members"]] == ["我的成員"]
    r = client.get(f"/cases/{couple.id}", headers=auth(world["staff"]))
    assert {m["name"] for m in r.json()["members"]} == {"我的成員", "別人的成員"}
