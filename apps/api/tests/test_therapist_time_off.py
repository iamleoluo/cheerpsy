"""心理師「這段不接案」：心理師管自己的、行政管全部；預約落在請假時段 409（batch 逐筆列出）；
別人看不到請假原因，也不能動別人的請假。"""

from datetime import datetime, timedelta, timezone

import pytest

REASON = "家人手術請假保密原因"


def _t(days=3, hour=10, minutes=60):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(minutes=minutes)


@pytest.fixture()
def world(make_user, make_case, room):
    t1, t2 = make_user("therapist", name="林一心理師"), make_user("therapist", name="陳二心理師")
    staff, admin = make_user("staff"), make_user("admin")
    c1, c2 = make_case(t1, "個案一"), make_case(t2, "個案二")
    return dict(t1=t1, t2=t2, staff=staff, admin=admin, c1=c1, c2=c2, room=room)


def off(client, auth, who, s, e, reason=REASON, **extra):
    return client.post("/therapist-time-off", headers=auth(who), json={
        "start_time": s.isoformat(), "end_time": e.isoformat(), "reason": reason, **extra})


def book(client, auth, who, case, room, s, e):
    return client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat()})


def test_therapist_manages_own_time_off(client, auth, world):
    w = world
    s, e = _t()
    r = off(client, auth, w["t1"], s, e)
    assert r.status_code == 201 and r.json()["therapist_id"] == w["t1"].id and r.json()["reason"] == REASON
    lst = client.get("/therapist-time-off", headers=auth(w["t1"])).json()
    assert [x["id"] for x in lst] == [r.json()["id"]]
    assert client.delete(f"/therapist-time-off/{r.json()['id']}", headers=auth(w["t1"])).status_code == 204
    assert client.get("/therapist-time-off", headers=auth(w["t1"])).json() == []
    assert off(client, auth, w["t1"], e, s).status_code == 422  # 結束早於開始


def test_staff_and_admin_manage_any_therapist(client, auth, world):
    w = world
    s, e = _t()
    assert off(client, auth, w["staff"], s, e).status_code == 422  # 行政要指定心理師
    r = off(client, auth, w["staff"], s, e, therapist_id=w["t2"].id)
    assert r.status_code == 201 and r.json()["therapist_id"] == w["t2"].id
    r2 = off(client, auth, w["admin"], s, e, therapist_id=w["t1"].id)
    assert r2.status_code == 201
    assert len(client.get("/therapist-time-off", headers=auth(w["staff"])).json()) == 2
    assert client.get(f"/therapist-time-off?therapist_id={w['t2'].id}", headers=auth(w["admin"])).json()[0]["reason"] == REASON
    assert client.delete(f"/therapist-time-off/{r.json()['id']}", headers=auth(w["staff"])).status_code == 204
    # 不是心理師的人不能被請假
    assert off(client, auth, w["admin"], s, e, therapist_id=w["staff"].id).status_code == 404


def test_other_therapists_cannot_see_or_touch_time_off_or_its_reason(client, auth, world):
    w = world
    s, e = _t()
    mine = off(client, auth, w["t1"], s, e).json()["id"]
    h2 = auth(w["t2"])
    assert client.get("/therapist-time-off", headers=h2).json() == []  # 列表只有自己的
    assert client.get(f"/therapist-time-off?therapist_id={w['t1'].id}", headers=h2).status_code == 404
    assert client.get("/therapist-time-off/blocked", headers=h2,
                      params={"therapist_id": w["t1"].id, "start": s.isoformat(), "end": e.isoformat()}).status_code == 404
    # 刪別人的與刪不存在的回應相同
    gone = client.delete(f"/therapist-time-off/{mine}", headers=h2)
    miss = client.delete("/therapist-time-off/999999", headers=h2)
    assert gone.status_code == miss.status_code == 404 and gone.json() == miss.json()
    assert off(client, auth, w["t2"], s, e, therapist_id=w["t1"].id).status_code == 404  # 不能替別人請假
    assert len(client.get("/therapist-time-off", headers=auth(w["t1"])).json()) == 1  # 沒被刪掉


def test_blocked_view_never_contains_the_reason(client, auth, world):
    w = world
    s, e = _t()
    off(client, auth, w["t1"], s, e)
    q = {"therapist_id": w["t1"].id, "start": (s - timedelta(hours=1)).isoformat(), "end": (e + timedelta(hours=1)).isoformat()}
    for who in (w["staff"], w["admin"], w["t1"]):
        r = client.get("/therapist-time-off/blocked", headers=auth(who), params=q)
        assert r.status_code == 200 and len(r.json()) == 1
        assert "reason" not in r.json()[0] and REASON not in r.text
    # 範圍外沒有
    far = {"therapist_id": w["t1"].id, "start": (e + timedelta(days=2)).isoformat(), "end": (e + timedelta(days=3)).isoformat()}
    assert client.get("/therapist-time-off/blocked", headers=auth(w["staff"]), params=far).json() == []


def test_booking_inside_time_off_is_409_without_the_reason(client, auth, world):
    w = world
    s, e = _t()
    off(client, auth, w["t1"], s, e)
    for who in (w["staff"], w["t1"]):
        r = book(client, auth, who, w["c1"], w["room"], s + timedelta(minutes=30), e + timedelta(minutes=30))
        assert r.status_code == 409 and "不接案" in r.json()["detail"]
        assert REASON not in r.text and "林一心理師" not in r.text and "個案一" not in r.text
    # 首尾相接可以；別的心理師不受影響
    assert book(client, auth, w["staff"], w["c1"], w["room"], e, e + timedelta(hours=1)).status_code == 201
    assert book(client, auth, w["staff"], w["c2"], w["room"], s, e).status_code == 201
    # 刪掉請假後可以約
    tid = client.get("/therapist-time-off", headers=auth(w["t1"])).json()[0]["id"]
    client.delete(f"/therapist-time-off/{tid}", headers=auth(w["t1"]))
    s9, e9 = _t(days=9)
    assert book(client, auth, w["staff"], w["c1"], w["room"], s9, e9).status_code == 201


def test_reschedule_into_time_off_is_409(client, auth, world):
    w = world
    s, e = _t()
    a = book(client, auth, w["staff"], w["c1"], w["room"], s - timedelta(days=1), e - timedelta(days=1)).json()["id"]
    off(client, auth, w["t1"], s, e)
    r = client.put(f"/appointments/{a}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 409 and "不接案" in r.json()["detail"] and REASON not in r.text
    # 只換診間、時間沒動：不重查
    assert client.put(f"/appointments/{a}", headers=auth(w["staff"]), json={"room_id": w["room"].id}).status_code == 200


def test_batch_lists_each_slot_in_time_off_and_creates_nothing(client, auth, world):
    w = world
    s1, e1 = _t(days=3)
    s2, e2 = _t(days=4)
    s3, e3 = _t(days=5)
    off(client, auth, w["t1"], s1, e1)
    off(client, auth, w["t1"], s3, e3)
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["c1"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": x.isoformat(), "end_time": y.isoformat()} for x, y in ((s1, e1), (s2, e2), (s3, e3))]})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert "第 1 筆" in d and "第 3 筆" in d and "第 2 筆" not in d and REASON not in d
    assert client.get("/appointments", headers=auth(w["staff"])).json() == []  # 整批不成立
    ok = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["c1"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s2.isoformat(), "end_time": e2.isoformat()}]})
    assert ok.status_code == 201


def test_creating_time_off_reports_existing_bookings_but_keeps_them(client, auth, world):
    w = world
    s, e = _t()
    book(client, auth, w["staff"], w["c1"], w["room"], s, e)
    r = off(client, auth, w["t1"], s - timedelta(hours=1), e + timedelta(hours=1))
    assert r.status_code == 201 and r.json()["overlapping_appointments"] == 1
    assert len(client.get("/appointments", headers=auth(w["staff"])).json()) == 1  # 不會被取消


def test_referral_convert_respects_time_off(client, auth, world, db):
    from app.models.referral import (ReferralDispatch, ReferralDispatchTarget, ReferralRequest, ReferralSlotOffer)
    from app.services import slot_check

    w = world
    r = ReferralRequest(dispatch_code="261117002", name="新個案", consultation_mode="individual", status="converted")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1)
    db.add(d)
    db.flush()
    t = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=w["t1"].id, status="accepted")
    db.add(t)
    db.flush()
    s, e = _t()
    day = s.astimezone(slot_check.TZ).date()
    slot = ReferralSlotOffer(target_id=t.id, seq=1, slot_date=day, start_time="10:00", end_time="11:00")
    db.add(slot)
    db.commit()
    start = datetime.fromisoformat(f"{day}T10:00:00+08:00")
    off(client, auth, w["t1"], start - timedelta(hours=1), start + timedelta(hours=2))
    r1 = client.post(f"/referrals/{r.id}/convert", headers=auth(w["staff"]),
                     json={"slot_id": slot.id, "session_type": "online", "amount": 1200})
    assert r1.status_code == 409 and "不接案" in r1.json()["detail"] and REASON not in r1.text


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_only_adds_the_table_and_roundtrips():
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text

    from app.database import engine

    spec = importlib.util.spec_from_file_location(
        "zv2f", Path(__file__).resolve().parent.parent / "alembic" / "versions" / "zv2f6a7b8c9d_therapist_time_off.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "zu1e5f6a7b8c"
    before = set(inspect(engine).get_table_names()) - {"therapist_time_off"}
    with engine.begin() as c:
        c.execute(text("DROP TABLE therapist_time_off"))
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        assert set(inspect(engine).get_table_names()) == before | {"therapist_time_off"}  # 只多這一張
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
        assert set(inspect(engine).get_table_names()) == before
    finally:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            if "therapist_time_off" not in inspect(engine).get_table_names():
                mod.upgrade()
