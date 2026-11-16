"""儀表板「昨日仍待報到」：開始時間早於今天 00:00（Asia/Taipei）且仍為 booked。"""

from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=8))


def today0():
    return datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture()
def world(make_user, make_case, make_appt, room):
    a, b = make_user("therapist", name="甲心理師"), make_user("therapist", name="乙心理師")
    return dict(a=a, b=b, staff=make_user("staff"), admin=make_user("admin"), room=room,
                ca=make_case(a, "甲的個案"), cb=make_case(b, "乙的個案"), make_appt=make_appt)


def get(client, auth, who):
    r = client.get("/dashboard/pending-checkin", headers=auth(who))
    assert r.status_code == 200, r.text
    return r.json()


def test_timezone_boundary(client, auth, world):
    w = world
    t0 = today0()
    yest = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 - timedelta(minutes=30))  # 昨天 23:30
    w["make_appt"](w["ca"], w["a"], w["room"], start=t0 + timedelta(minutes=30))  # 今天 00:30
    out = get(client, auth, w["staff"])
    assert out["count"] == 1 and [i["appointment_id"] for i in out["items"]] == [yest.id]
    i = out["items"][0]
    assert i["therapist_name"] == "甲心理師" and i["subject_name"] == "甲的個案" and i["session_type"]
    assert not i["is_intake"]


def test_only_last_30_days_newest_first(client, auth, world):
    w = world
    t0 = today0()
    old31 = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 - timedelta(days=31))  # 31 天前：不列
    edge = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 - timedelta(days=30))  # 剛好 30 天前 00:00：列
    mid = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 - timedelta(days=10))
    new = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 - timedelta(days=1))
    out = get(client, auth, w["staff"])
    ids = [i["appointment_id"] for i in out["items"]]
    assert ids == [new.id, mid.id, edge.id]  # 從新排到舊
    assert old31.id not in ids and out["count"] == 3  # count 也只算這 30 天
    assert get(client, auth, w["a"])["count"] == 3


def test_exactly_midnight_today_is_not_listed(client, auth, world):
    w = world
    w["make_appt"](w["ca"], w["a"], w["room"], start=today0())
    assert get(client, auth, w["admin"])["count"] == 0


def test_executed_and_cancelled_not_listed(client, auth, world, db):
    w = world
    old = today0() - timedelta(days=2)
    booked = w["make_appt"](w["ca"], w["a"], w["room"], start=old)
    done = w["make_appt"](w["ca"], w["a"], w["room"], start=old + timedelta(hours=3))
    gone = w["make_appt"](w["ca"], w["a"], w["room"], start=old + timedelta(hours=6))
    done.status, gone.status = "executed", "cancelled"
    db.commit()
    assert [i["appointment_id"] for i in get(client, auth, w["staff"])["items"]] == [booked.id]


def test_therapist_sees_only_own(client, auth, world):
    w = world
    old = today0() - timedelta(days=1, hours=-1)
    mine = w["make_appt"](w["ca"], w["a"], w["room"], start=old)
    theirs = w["make_appt"](w["cb"], w["b"], w["room"], start=old + timedelta(hours=3))
    out = get(client, auth, w["a"])
    assert [i["appointment_id"] for i in out["items"]] == [mine.id] and out["count"] == 1
    assert "乙" not in str(out)
    assert {i["appointment_id"] for i in get(client, auth, w["staff"])["items"]} == {mine.id, theirs.id}
    assert get(client, auth, w["admin"])["count"] == 2


def test_does_not_change_any_status(client, auth, world, db):
    w = world
    a = w["make_appt"](w["ca"], w["a"], w["room"], start=today0() - timedelta(days=3))
    get(client, auth, w["staff"])
    db.refresh(a)
    assert a.status == "booked" and a.checkin_status == "pending"


def test_intake_appointment_shows_referral_name(client, auth, world, db):
    from app.models.referral import ReferralRequest

    w = world
    r = ReferralRequest(dispatch_code="261117300", name="初診對象", consultation_mode="individual", status="converted")
    db.add(r)
    db.flush()
    a = w["make_appt"](w["ca"], w["a"], w["room"], start=today0() - timedelta(days=1))
    a.case_id, a.referral_id, a.is_intake = None, r.id, True
    db.commit()
    i = get(client, auth, w["staff"])["items"][0]
    assert i["subject_name"] == "初診對象" and i["is_intake"] is True


def test_requires_login(client):
    assert client.get("/dashboard/pending-checkin").status_code in (401, 403)


def test_times_are_serialised_in_taipei_time(client, auth, world):
    w = world
    w["make_appt"](w["ca"], w["a"], w["room"], start=today0() - timedelta(minutes=30))
    i = get(client, auth, w["staff"])["items"][0]
    assert i["start_time"].endswith("+08:00") and i["start_time"][11:16] == "23:30"
