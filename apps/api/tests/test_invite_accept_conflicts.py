"""承接時檢查：心理師提出的每個時段都要沒有預約、沒有不接案；409 逐筆列出第幾個時段，只寫時段。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.referral import ReferralDispatch, ReferralDispatchTarget, ReferralRequest

REASON = "私人不接案原因"


def _day(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).astimezone().date()


@pytest.fixture()
def world(make_user, make_case, room, db):
    t1 = make_user("therapist", name="林一心理師")
    staff = make_user("staff")
    c = make_case(t1, "個案一")
    r = ReferralRequest(dispatch_code="261117100", name="新個案", consultation_mode="individual", status="matching")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1)
    db.add(d)
    db.flush()
    t = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=t1.id, status="pending")
    db.add(t)
    db.commit()
    return dict(t1=t1, staff=staff, case=c, room=room, target=t)


def _tw(day, h):
    return datetime.fromisoformat(f"{day}T{h:02d}:00:00+08:00")


def accept(client, auth, w, slots):
    return client.post(f"/referrals/invites/{w['target'].id}/accept", headers=auth(w["t1"]), json={
        "slots": [{"slot_date": str(d), "start_time": a, "end_time": b} for d, a, b in slots]})


def test_accept_ok_when_free(client, auth, world):
    r = accept(client, auth, world, [(_day(5), "10:00", "11:00"), (_day(6), "10:00", "11:00")])
    assert r.status_code == 200, r.text


def test_accept_409_lists_each_conflicting_slot_without_names_or_reason(client, auth, world):
    w = world
    d1, d2, d3 = _day(5), _day(6), _day(7)
    client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": _tw(d1, 10).isoformat(), "end_time": _tw(d1, 11).isoformat()})
    client.post("/therapist-time-off", headers=auth(w["t1"]), json={
        "start_time": _tw(d3, 9).isoformat(), "end_time": _tw(d3, 12).isoformat(), "reason": REASON})
    r = accept(client, auth, w, [(d1, "10:30", "11:30"), (d2, "10:00", "11:00"), (d3, "10:00", "11:00")])
    assert r.status_code == 409
    d = r.json()["detail"]
    assert "第 1 個時段" in d and "第 3 個時段" in d and "第 2 個時段" not in d
    assert "已有其他預約" in d and "不接案" in d
    for bad in (REASON, "林一心理師", "個案一", "新個案"):
        assert bad not in d
    # 失敗不改狀態：改好時段後仍可承接
    again = accept(client, auth, w, [(d2, "10:00", "11:00")])
    assert again.status_code == 200 and again.json()["status"] == "accepted"


def test_adjacent_slot_is_fine(client, auth, world):
    w = world
    d = _day(5)
    client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": _tw(d, 10).isoformat(), "end_time": _tw(d, 11).isoformat()})
    assert accept(client, auth, w, [(d, "11:00", "12:00")]).status_code == 200


def test_bad_time_is_422(client, auth, world):
    assert accept(client, auth, world, [(_day(5), "11:00", "10:00")]).status_code == 422
