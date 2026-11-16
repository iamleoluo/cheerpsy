"""GET /rooms/availability?therapist_id=：排除該心理師已有預約與不接案的時段；不帶時行為不變。"""

from datetime import datetime, timedelta, timezone

import pytest

REASON = "私人不接案原因"


def _t(days=3, hour=10, minutes=60):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(minutes=minutes)


@pytest.fixture()
def world(make_user, make_case, room):
    t1, t2 = make_user("therapist", name="林一心理師"), make_user("therapist", name="陳二心理師")
    return dict(t1=t1, t2=t2, staff=make_user("staff"), admin=make_user("admin"),
                c1=make_case(t1, "個案一"), c2=make_case(t2, "個案二"), room=room)


def avail(client, auth, who, s, e, **params):
    return client.get("/rooms/availability", headers=auth(who),
                      params={"start": s.isoformat(), "end": e.isoformat(), **params})


def book(client, auth, world, case, s, e):
    r = client.post("/appointments", headers=auth(world["staff"]), json={
        "case_id": case.id, "room_id": world["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 201, r.text


def test_without_therapist_id_behaviour_unchanged(client, auth, world):
    w = world
    s, e = _t()
    ids = {r["id"] for r in avail(client, auth, w["staff"], s, e).json()}
    assert w["room"].id in ids
    # 心理師有預約／不接案都不影響不帶 therapist_id 的結果（只有診間被佔才會少）
    client.post("/therapist-time-off", headers=auth(w["t1"]),
                json={"start_time": s.isoformat(), "end_time": e.isoformat(), "reason": REASON})
    assert {r["id"] for r in avail(client, auth, w["staff"], s, e).json()} == ids


def test_therapist_id_excludes_booked_slot(client, auth, world):
    w = world
    s, e = _t()
    book(client, auth, w, w["c1"], s, e)
    assert avail(client, auth, w["staff"], s, e, therapist_id=w["t1"].id).json() == []
    # 部分重疊也算；首尾相接不算
    assert avail(client, auth, w["staff"], s + timedelta(minutes=30), e + timedelta(minutes=30),
                 therapist_id=w["t1"].id).json() == []
    r = avail(client, auth, w["staff"], e, e + timedelta(hours=1), therapist_id=w["t1"].id).json()
    assert w["room"].id in {x["id"] for x in r}
    # 另一位心理師同一時段：診間被佔所以空，但換個診間時段不受 t1 影響
    s2, e2 = _t(days=4)
    r = avail(client, auth, w["staff"], s2, e2, therapist_id=w["t2"].id).json()
    assert w["room"].id in {x["id"] for x in r}


def test_therapist_id_excludes_time_off_without_leaking_reason_or_names(client, auth, world):
    w = world
    s, e = _t()
    client.post("/therapist-time-off", headers=auth(w["t1"]),
                json={"start_time": s.isoformat(), "end_time": e.isoformat(), "reason": REASON})
    r = avail(client, auth, w["staff"], s, e, therapist_id=w["t1"].id)
    assert r.status_code == 200 and r.json() == []
    s2, e2 = _t(days=4)
    ok = avail(client, auth, w["staff"], s2, e2, therapist_id=w["t1"].id)
    for bad in (REASON, "林一心理師", "個案一"):
        assert bad not in r.text and bad not in ok.text
    assert {"id", "room_code"} <= set(ok.json()[0])


def test_cancelled_booking_frees_the_slot(client, auth, world):
    w = world
    s, e = _t()
    r = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["c1"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat()})
    client.put(f"/appointments/{r.json()['id']}/cancel", headers=auth(w["staff"]))
    assert w["room"].id in {x["id"] for x in avail(client, auth, w["staff"], s, e, therapist_id=w["t1"].id).json()}


def test_exclude_appointment_id_with_therapist(client, auth, world):
    w = world
    s, e = _t()
    r = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["c1"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat()})
    aid = r.json()["id"]
    got = avail(client, auth, w["staff"], s, e, therapist_id=w["t1"].id, exclude_appointment_id=aid).json()
    assert w["room"].id in {x["id"] for x in got}


def test_therapist_can_only_query_self(client, auth, world):
    w = world
    s, e = _t()
    assert avail(client, auth, w["t1"], s, e, therapist_id=w["t1"].id).status_code == 200
    assert avail(client, auth, w["t1"], s, e, therapist_id=w["t2"].id).status_code == 404
    # 不是心理師的 id、不存在的 id 一樣 404
    assert avail(client, auth, w["admin"], s, e, therapist_id=w["staff"].id).status_code == 404
    assert avail(client, auth, w["admin"], s, e, therapist_id=999999).status_code == 404
    assert avail(client, auth, w["admin"], s, e, therapist_id=w["t2"].id).status_code == 200
