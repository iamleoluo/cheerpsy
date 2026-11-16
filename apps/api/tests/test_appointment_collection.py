"""收款記錄：只記狀態（未收／已收／免收）、方式、時間、經手人。不產生 session_records、流水、核銷、對帳。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.appointment import Appointment


def _slot(days=3, hour=10):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=1)


@pytest.fixture()
def world(make_user, make_case, room):
    a, b = make_user("therapist", name="甲心理師"), make_user("therapist", name="乙心理師")
    staff, admin, acct = make_user("staff"), make_user("admin"), make_user("accountant")
    return dict(a=a, b=b, staff=staff, admin=admin, acct=acct, room=room,
                case_a=make_case(a, "甲的個案"), case_b=make_case(b, "乙的個案"))


def book(client, auth, who, case, room, day=3, **extra):
    s, e = _slot(day)
    r = client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1500,
        "start_time": s.isoformat(), "end_time": e.isoformat(), **extra})
    assert r.status_code == 201, r.text
    return r.json()


def collect(client, auth, who, appt_id, **body):
    return client.put(f"/appointments/{appt_id}/collection", headers=auth(who), json=body)


@pytest.mark.parametrize("who", ["staff", "admin"])
def test_record_paid_with_method_time_and_handler(client, auth, world, db, who):
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    assert (a["payment_status"], a["payment_method"], a["paid_at"]) == ("unpaid", None, None)  # 預設未收
    r = collect(client, auth, w[who], a["id"], payment_status="paid", payment_method="transfer")
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["payment_status"], j["payment_method"]) == ("paid", "transfer")
    assert j["paid_at"] and j["paid_by_name"] == w[who].name
    # 改回未收：方式、時間、經手人清掉
    j = collect(client, auth, w[who], a["id"], payment_status="unpaid", payment_method="cash").json()
    assert (j["payment_status"], j["payment_method"], j["paid_at"], j["paid_by_name"]) == ("unpaid", None, None, None)
    # 免收
    j = collect(client, auth, w[who], a["id"], payment_status="waived").json()
    assert (j["payment_status"], j["payment_method"]) == ("waived", None) and j["paid_at"]


def test_paid_requires_valid_method_and_status_must_be_known(client, auth, world):
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    assert collect(client, auth, w["staff"], a["id"], payment_status="paid").status_code == 400
    assert collect(client, auth, w["staff"], a["id"], payment_status="paid", payment_method="bitcoin").status_code == 400
    assert collect(client, auth, w["staff"], a["id"], payment_status="refunded").status_code == 400


def test_collection_creates_no_ledger_or_claim_records(client, auth, world, db):
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    collect(client, auth, w["staff"], a["id"], payment_status="paid", payment_method="cash")
    client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"]))
    for table in ("session_records", "claim_batches", "invoices", "petty_cash", "product_sales", "therapist_payouts"):
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table


def test_collection_is_audited(client, auth, world, db):
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    collect(client, auth, w["staff"], a["id"], payment_status="paid", payment_method="card")
    rows = db.execute(text("SELECT after_data FROM audit_log WHERE table_name='appointments' AND record_id=:i ORDER BY id"),
                      {"i": a["id"]}).all()
    assert any((r.after_data or {}).get("payment_method") == "card" for r in rows)


def test_cancelled_appointment_cannot_be_collected(client, auth, world):
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    assert collect(client, auth, w["staff"], a["id"], payment_status="paid", payment_method="cash").status_code == 400


# ---- 心理師：只看得到自己個案的收款狀態，不能改；別人的 404 ----------------------
def test_therapist_sees_own_status_but_cannot_record_or_touch_others(client, auth, world):
    w = world
    mine = book(client, auth, w["staff"], w["case_a"], w["room"], day=3)
    theirs = book(client, auth, w["staff"], w["case_b"], w["room"], day=4)
    collect(client, auth, w["staff"], mine["id"], payment_status="paid", payment_method="cash")
    seen = client.get(f"/appointments/{mine['id']}", headers=auth(w["a"])).json()
    assert (seen["payment_status"], seen["payment_method"]) == ("paid", "cash")
    assert collect(client, auth, w["a"], mine["id"], payment_status="unpaid").status_code == 403  # 不能改
    other = collect(client, auth, w["a"], theirs["id"], payment_status="paid", payment_method="cash")
    assert other.status_code == 403  # 角色不符，連存在與否都不透露
    assert client.get(f"/appointments/{theirs['id']}", headers=auth(w["a"])).status_code == 404
    listing = client.get("/appointments", headers=auth(w["a"])).json()
    assert [x["id"] for x in listing] == [mine["id"]]
    # 會計：維持現狀
    assert collect(client, auth, w["acct"], mine["id"], payment_status="paid", payment_method="cash").status_code == 403


def test_collection_does_not_trigger_google_resync(client, auth, world, db):
    from app.models.gcal import GcalOutbox, GoogleOAuthConnection
    from app.services import google_oauth

    db.add(GoogleOAuthConnection(id=1, google_email="owner@example.com", status="active", refresh_token_enc="x",
                                 scopes=" ".join(google_oauth.CALENDAR_SCOPES)))
    db.commit()
    w = world
    a = book(client, auth, w["staff"], w["case_a"], w["room"])
    db.query(GcalOutbox).delete()
    db.commit()
    collect(client, auth, w["staff"], a["id"], payment_status="paid", payment_method="cash")
    db.expire_all()
    assert db.query(GcalOutbox).count() == 0  # 收款不影響事件內容
