"""失約費：應收提示。金額存在 clinic_settings，未到時帶出建議；行政可改或免收；不產生流水或核銷。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text


@pytest.fixture()
def world(make_user, make_case, room):
    a, b = make_user("therapist", name="甲"), make_user("therapist", name="乙")
    return dict(a=a, b=b, staff=make_user("staff"), admin=make_user("admin"), room=room,
                case_a=make_case(a, "甲案"), case_b=make_case(b, "乙案"))


def book(client, auth, w, case, day):
    s = (datetime.now(timezone.utc) + timedelta(days=day)).replace(hour=10, minute=0, second=0, microsecond=0)
    r = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": case.id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1500,
        "start_time": s.isoformat(), "end_time": (s + timedelta(hours=1)).isoformat()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_defaults_and_admin_can_change_settings(client, auth, world):
    w = world
    d = client.get("/settings/no-show-fees", headers=auth(w["a"])).json()  # 心理師也讀得到
    assert d == {"advance_notice": 0, "late_cancel": 200, "no_notice": 500}
    assert client.patch("/settings/clinic", headers=auth(w["staff"]), json={"no_show_fee_late_cancel": 300}).status_code == 403
    r = client.patch("/settings/clinic", headers=auth(w["admin"]), json={"no_show_fee_late_cancel": 350, "no_show_fee_no_notice": 800})
    assert r.status_code == 200 and r.json()["no_show_fee_late_cancel"] == 350
    assert client.get("/settings/no-show-fees", headers=auth(w["staff"])).json()["no_notice"] == 800
    assert client.patch("/settings/clinic", headers=auth(w["admin"]), json={"no_show_fee_late_cancel": -1}).status_code == 422


@pytest.mark.parametrize("kind,fee", [("advance_notice", 0), ("late_cancel", 200), ("no_notice", 500)])
def test_absent_suggests_fee_from_settings(client, auth, world, kind, fee):
    w = world
    aid = book(client, auth, w, w["case_a"], 3)
    r = client.put(f"/appointments/{aid}/absent", headers=auth(w["staff"]), json={"no_show_type": kind})
    assert r.status_code == 200 and r.json()["no_show_fee"] == fee


def test_staff_can_override_or_waive_and_adjust_later(client, auth, world, db):
    w = world
    a1, a2 = book(client, auth, w, w["case_a"], 3), book(client, auth, w, w["case_a"], 4)
    r = client.put(f"/appointments/{a1}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice", "no_show_fee": 0})
    assert r.json()["no_show_fee"] == 0  # 免收
    client.put(f"/appointments/{a2}/absent", headers=auth(w["staff"]), json={"no_show_type": "late_cancel"})
    r = client.put(f"/appointments/{a2}/no-show-fee", headers=auth(w["staff"]), json={"no_show_fee": 123})
    assert r.json()["no_show_fee"] == 123
    assert client.put(f"/appointments/{a2}/no-show-fee", headers=auth(w["a"]), json={"no_show_fee": 0}).status_code == 403
    aud = db.execute(text("SELECT after_data FROM audit_log WHERE table_name='appointments' AND record_id=:i"), {"i": a2}).all()
    assert any((x.after_data or {}).get("no_show_fee") == 123 for x in aud)


def test_therapist_cannot_set_fee_and_sees_only_own(client, auth, world):
    w = world
    mine, theirs = book(client, auth, w, w["case_a"], 3), book(client, auth, w, w["case_b"], 4)
    r = client.put(f"/appointments/{mine}/absent", headers=auth(w["a"]), json={"no_show_type": "no_notice", "no_show_fee": 0})
    assert r.status_code == 200 and r.json()["no_show_fee"] == 500  # 心理師送的金額被忽略
    assert client.put(f"/appointments/{theirs}/absent", headers=auth(w["a"]), json={"no_show_type": "no_notice"}).status_code == 404


def test_no_show_fee_only_for_no_show_and_creates_no_ledger(client, auth, world, db):
    w = world
    aid = book(client, auth, w, w["case_a"], 3)
    assert client.put(f"/appointments/{aid}/no-show-fee", headers=auth(w["staff"]), json={"no_show_fee": 10}).status_code == 400
    client.put(f"/appointments/{aid}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice"})
    for t in ("session_records", "claim_batches", "petty_cash", "therapist_payouts"):
        assert db.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0, t
