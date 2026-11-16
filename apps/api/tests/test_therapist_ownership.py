"""隔離的單位是「心理師」，不是「欄位」。

心理師對自己的個案與預約有完整權限（含金額、時間、診間、狀態），完全看不到、碰不到其他心理師的：
別人的預約與個案，讀、改、取消、刪除一律 404，而且與「根本不存在」的 404 一模一樣（不能用 id 猜出存在與否）。
行政（staff）與管理員（admin）可看可改全部。會計維持現狀。
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.appointment import Appointment
from app.models.case import Case
from app.models.room import Room

B_NAME = "乙的個案陳大文"
B_AMOUNT = 7777


def _slot(days=3, hour=10, hours=1):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=hours)


@pytest.fixture()
def world(make_user, make_case, room, db):
    a = make_user("therapist", name="甲心理師")
    b = make_user("therapist", name="乙心理師")
    staff, admin, acct = make_user("staff"), make_user("admin"), make_user("accountant")
    case_a = make_case(a, "甲的個案")
    case_b = make_case(b, B_NAME, phone="0988-111-222")
    couple_b = make_case(b, "乙的伴侶案", case_type="couple")
    room2 = Room(name="晤談室 3C", floor=3, room_code="3C")
    db.add(room2)
    db.commit()
    return dict(a=a, b=b, staff=staff, admin=admin, acct=acct, case_a=case_a, case_b=case_b,
                couple_b=couple_b, room=room, room2=room2)


def post(client, auth, who, case, room, day=3, hour=10, **extra):
    s, e = _slot(day, hour)
    body = {"case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1000,
            "start_time": s.isoformat(), "end_time": e.isoformat(), **extra}
    return client.post("/appointments", json=body, headers=auth(who))


def b_appt(client, auth, w, amount=B_AMOUNT, day=4):
    r = post(client, auth, w["b"], w["case_b"], w["room"], day=day, amount=amount)
    assert r.status_code == 201, r.text
    return r.json()


def db_row(db, appt_id):
    db.expire_all()
    return db.get(Appointment, appt_id)


# ---------------------------------------------------------------------------
# 心理師對自己的預約：完整權限，含金額；API 回真實金額
# ---------------------------------------------------------------------------
def test_owner_creates_edits_amount_and_api_returns_real_amount(client, auth, world, db):
    w = world
    r = post(client, auth, w["a"], w["case_a"], w["room"], amount=1500)
    assert r.status_code == 201, r.text
    appt = r.json()
    assert appt["amount"] == 1500 and float(db_row(db, appt["id"]).amount) == 1500  # 不是 0
    # 修改：金額、時間、診間
    s, e = _slot(5, 14)
    r = client.put(f"/appointments/{appt['id']}", headers=auth(w["a"]),
                   json={"amount": 1800, "start_time": s.isoformat(), "end_time": e.isoformat(), "room_id": w["room2"].id})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 1800 and r.json()["room_id"] == w["room2"].id
    # 讀：單筆與列表都是真實金額
    assert client.get(f"/appointments/{appt['id']}", headers=auth(w["a"])).json()["amount"] == 1800
    assert [x["amount"] for x in client.get("/appointments", headers=auth(w["a"])).json()] == [1800]
    # 清除與驗證
    assert client.put(f"/appointments/{appt['id']}", headers=auth(w["a"]), json={"amount": 0}).status_code == 422
    assert client.put(f"/appointments/{appt['id']}", headers=auth(w["a"]), json={"amount": -1}).status_code == 422
    assert post(client, auth, w["a"], w["case_a"], w["room"], day=9, amount=10_000_000).status_code == 422


def test_owner_batch_create_with_amount(client, auth, world):
    w = world
    s1, e1 = _slot(6)
    s2, e2 = _slot(13)
    r = client.post("/appointments/batch", headers=auth(w["a"]), json={
        "case_id": w["case_a"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 2000,
        "slots": [{"start_time": s1.isoformat(), "end_time": e1.isoformat()},
                  {"start_time": s2.isoformat(), "end_time": e2.isoformat()}]})
    assert r.status_code == 201, r.text
    assert [x["amount"] for x in r.json()] == [2000, 2000]


def test_owner_can_change_status_of_own_appointments(client, auth, world, db):
    w = world
    a1 = post(client, auth, w["a"], w["case_a"], w["room"], day=3).json()
    a2 = post(client, auth, w["a"], w["case_a"], w["room"], day=4).json()
    a3 = post(client, auth, w["a"], w["case_a"], w["room"], day=5).json()
    assert client.put(f"/appointments/{a1['id']}/arrive", headers=auth(w["a"])).json()["status"] == "executed"
    r = client.put(f"/appointments/{a2['id']}/absent", headers=auth(w["a"]), json={"no_show_type": "no_notice"})
    assert r.status_code == 200 and r.json()["status"] == "no_show"
    assert client.put(f"/appointments/{a3['id']}/cancel", headers=auth(w["a"])).json()["status"] == "cancelled"


def test_owner_can_edit_own_case_but_not_reassign_or_change_status(client, auth, world, db):
    w = world
    h = auth(w["a"])
    r = client.put(f"/cases/{w['case_a'].id}", headers=h, json={"notes": "我的備註", "phone": "0900-000-001"})
    assert r.status_code == 200 and r.json()["phone"] == "0900-000-001"
    # 不能改派給乙，也不能自行改個案狀態
    assert client.put(f"/cases/{w['case_a'].id}", headers=h, json={"therapist_id": w["b"].id}).status_code == 403
    assert client.put(f"/cases/{w['case_a'].id}", headers=h, json={"status": "closed"}).status_code == 403
    db.expire_all()
    c = db.get(Case, w["case_a"].id)
    assert c.therapist_id == w["a"].id and c.status != "closed"
    # 建立個案時指定乙，仍是甲自己的
    r = client.post("/cases", headers=h, json={"name": "新個案", "therapist_id": w["b"].id, "funding_source": "self_pay"})
    assert r.status_code == 201 and r.json()["therapist_id"] == w["a"].id


# ---------------------------------------------------------------------------
# 甲碰乙的預約／個案：全部被擋，與不存在的 id 回應一模一樣，連直接猜 id 也一樣
# ---------------------------------------------------------------------------
def test_cannot_read_edit_cancel_or_delete_others_appointment(client, auth, world, db):
    w = world
    h = auth(w["a"])
    bid = b_appt(client, auth, w)["id"]
    ghost = 999999
    s, e = _slot(8)
    probes = [
        ("get", f"/appointments/{{}}", None),
        ("put", f"/appointments/{{}}", {"amount": 1}),
        ("put", f"/appointments/{{}}", {"start_time": s.isoformat(), "end_time": e.isoformat()}),
        ("put", f"/appointments/{{}}/cancel", None),
        ("put", f"/appointments/{{}}/arrive", None),
        ("put", f"/appointments/{{}}/absent", {"no_show_type": "no_notice"}),
    ]
    for method, path, body in probes:
        kw = {"json": body} if body is not None else {}
        real = getattr(client, method)(path.format(bid), headers=h, **kw)
        miss = getattr(client, method)(path.format(ghost), headers=h, **kw)
        assert real.status_code == 404 and (real.status_code, real.json()) == (miss.status_code, miss.json()), (method, path)
    # 刪除：混著自己的與乙的 id → 整批 404，自己的也不會被刪（不能用刪除探測別人的）
    mine = post(client, auth, w["a"], w["case_a"], w["room"], day=7).json()["id"]
    real = client.request("DELETE", "/appointments", headers=h, json={"ids": [mine, bid]})
    assert real.status_code == 404 and str(bid) in real.json()["detail"]
    assert db_row(db, mine) is not None
    # 與完全不存在的 id 同樣的訊息形狀
    miss = client.request("DELETE", "/appointments", headers=h, json={"ids": [ghost]})
    assert miss.status_code == 404 and miss.json()["detail"].replace(str(ghost), "X") == real.json()["detail"].replace(str(bid), "X")
    # 乙的預約完全沒被動到
    row = db_row(db, bid)
    assert row.status == "booked" and float(row.amount) == B_AMOUNT and row.therapist_id == w["b"].id


def test_guessing_ids_only_ever_finds_own_appointments(client, auth, world):
    w = world
    own = post(client, auth, w["a"], w["case_a"], w["room"], day=3).json()["id"]
    for d in (4, 5, 6):
        b_appt(client, auth, w, day=d)
    found = [i for i in range(1, 30) if client.get(f"/appointments/{i}", headers=auth(w["a"])).status_code == 200]
    assert found == [own]


def test_cannot_delete_others_batch(client, auth, world, db):
    w = world
    s1, e1 = _slot(10)
    r = client.post("/appointments/batch", headers=auth(w["b"]), json={
        "case_id": w["case_b"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s1.isoformat(), "end_time": e1.isoformat()}]})
    batch_id = r.json()[0]["batch_id"]
    gone = client.request("DELETE", f"/appointments/batch?batch_id={batch_id}", headers=auth(w["a"]))
    miss = client.request("DELETE", "/appointments/batch?batch_id=zzzzzzzz", headers=auth(w["a"]))
    assert gone.status_code == 404 and gone.json() == miss.json()
    assert db.query(Appointment).filter(Appointment.batch_id == batch_id).count() == 1


def test_cannot_read_or_edit_others_case_including_guessing_ids(client, auth, world, db):
    w = world
    h = auth(w["a"])
    real = client.get(f"/cases/{w['case_b'].id}", headers=h)
    miss = client.get("/cases/999999", headers=h)
    assert real.status_code == 404 and real.json() == miss.json() and B_NAME not in real.text
    put = client.put(f"/cases/{w['case_b'].id}", headers=h, json={"name": "被改掉"})
    assert put.status_code == 404 and client.put("/cases/999999", headers=h, json={"name": "x"}).json() == put.json()
    db.expire_all()
    assert db.get(Case, w["case_b"].id).name == B_NAME
    mine = [i for i in range(1, 30) if client.get(f"/cases/{i}", headers=h).status_code == 200]
    assert mine == [w["case_a"].id]


# ---------------------------------------------------------------------------
# 不能改派、不能用別人的個案建預約
# ---------------------------------------------------------------------------
def test_cannot_create_with_others_case_or_couple_case(client, auth, world, db):
    w = world
    r = post(client, auth, w["a"], w["case_b"], w["room"])
    miss = client.post("/appointments", headers=auth(w["a"]), json={
        "case_id": 999999, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "start_time": _slot()[0].isoformat(), "end_time": _slot()[1].isoformat()})
    assert r.status_code == 404 and r.json() == miss.json()
    # 用自己的個案、但掛上乙的伴侶案
    r = post(client, auth, w["a"], w["case_a"], w["room"], couple_case_id=w["couple_b"].id)
    assert r.status_code == 404
    # 批次也一樣
    s, e = _slot(5)
    r = client.post("/appointments/batch", headers=auth(w["a"]), json={
        "case_id": w["case_b"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s.isoformat(), "end_time": e.isoformat()}]})
    assert r.status_code == 404
    assert db.query(Appointment).count() == 0


def test_cannot_reassign_appointment_to_another_therapist(client, auth, world, db):
    w = world
    mine = post(client, auth, w["a"], w["case_a"], w["room"]).json()
    # 更新與建立都沒有「負責心理師」欄位；硬塞 therapist_id 會被忽略，不會改派
    r = client.put(f"/appointments/{mine['id']}", headers=auth(w["a"]), json={"therapist_id": w["b"].id, "amount": 500})
    assert r.status_code == 200 and r.json()["therapist_id"] == w["a"].id
    r = post(client, auth, w["a"], w["case_a"], w["room"], day=6, therapist_id=w["b"].id)
    assert r.status_code == 201 and r.json()["therapist_id"] == w["a"].id
    assert db_row(db, mine["id"]).therapist_id == w["a"].id


# ---------------------------------------------------------------------------
# 列表、批次、佔用：不混入乙的資料
# ---------------------------------------------------------------------------
def test_lists_never_include_others_data(client, auth, world):
    w = world
    own = post(client, auth, w["a"], w["case_a"], w["room"], amount=100).json()["id"]
    bid = b_appt(client, auth, w)["id"]
    for path in ("/appointments", f"/appointments?case_id={w['case_b'].id}", f"/appointments?room_id={w['room'].id}",
                 f"/appointments?status=booked", f"/cases/{w['case_b'].id}"):
        r = client.get(path, headers=auth(w["a"]))
        blob = r.text
        assert B_NAME not in blob and "乙心理師" not in blob and str(B_AMOUNT) not in blob, path
        if r.status_code == 200 and isinstance(r.json(), list):
            assert {x["id"] for x in r.json()} <= {own} and bid not in {x["id"] for x in r.json()}
    cases = client.get("/cases", headers=auth(w["a"])).json()
    assert {c["id"] for c in cases} == {w["case_a"].id}
    assert client.get(f"/cases?q={B_NAME}", headers=auth(w["a"])).json() == []
    assert client.get(f"/cases?therapist_id={w['b'].id}", headers=auth(w["a"])).json() == [
        {**c} for c in client.get("/cases", headers=auth(w["a"])).json()]  # 指定乙也只回自己的


def test_others_slot_shows_only_as_occupied(client, auth, world):
    w = world
    b_appt(client, auth, w, amount=B_AMOUNT)
    s, e = _slot(1)
    r = client.get("/rooms/occupancy", params={"start": s.isoformat(), "end": (s + timedelta(days=10)).isoformat()}, headers=auth(w["a"]))
    assert r.status_code == 200 and r.json(), "乙的時段應顯示為已佔用"
    blob = json.dumps(r.json(), ensure_ascii=False)
    for secret in (B_NAME, "乙心理師", str(B_AMOUNT), "amount", "case", "therapist"):
        assert secret not in blob, secret


# ---------------------------------------------------------------------------
# 行政與管理員：全部可看可改；會計維持現狀
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["staff", "admin"])
def test_staff_and_admin_see_and_edit_everything(client, auth, world, db, who):
    w = world
    ma = post(client, auth, w["a"], w["case_a"], w["room"], amount=100).json()["id"]
    mb = b_appt(client, auth, w)["id"]
    rows = {x["id"]: x for x in client.get("/appointments", headers=auth(w[who])).json()}
    assert rows[ma]["amount"] == 100 and rows[mb]["amount"] == B_AMOUNT and rows[mb]["case_name"] == B_NAME
    assert client.get(f"/cases/{w['case_b'].id}", headers=auth(w[who])).json()["name"] == B_NAME
    r = client.put(f"/appointments/{mb}", headers=auth(w[who]), json={"amount": 8888})
    assert r.status_code == 200 and r.json()["amount"] == 8888 and r.json()["therapist_id"] == w["b"].id
    assert client.put(f"/cases/{w['case_b'].id}", headers=auth(w[who]), json={"notes": "行政備註"}).status_code == 200
    # 行政可替任何心理師的個案建立預約，金額照存
    r = post(client, auth, w[who], w["case_b"], w["room"], day=9, amount=950)
    assert r.status_code == 201 and r.json()["amount"] == 950 and r.json()["therapist_id"] == w["b"].id
    assert client.put(f"/appointments/{ma}/cancel", headers=auth(w[who])).status_code == 200


def test_accountant_unchanged(client, auth, world):
    w = world
    mine = post(client, auth, w["a"], w["case_a"], w["room"], amount=100).json()["id"]
    assert post(client, auth, w["acct"], w["case_a"], w["room"], day=8).status_code == 403  # 不能建立預約
    assert client.put(f"/appointments/{mine}", headers=auth(w["acct"]), json={"amount": 1}).status_code == 403
    assert client.get(f"/appointments/{mine}", headers=auth(w["acct"])).json()["amount"] == 0  # 記帳已移除，維持現狀


def test_therapist_cannot_delete_even_own_but_can_cancel(client, auth, world, db):
    w = world
    h = auth(w["a"])
    own = post(client, auth, w["a"], w["case_a"], w["room"], day=7).json()
    # 單筆（ids）與整批（batch_id）刪除：自己的也一律 403，資料不動
    assert client.request("DELETE", "/appointments", headers=h, json={"ids": [own["id"]]}).status_code == 403
    s8, e8 = _slot(8)
    bt = client.post("/appointments/batch", headers=h, json={
        "case_id": w["case_a"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s8.isoformat(), "end_time": e8.isoformat()}]}).json()[0]["batch_id"]
    assert client.request("DELETE", f"/appointments/batch?batch_id={bt}", headers=h).status_code == 403
    assert db_row(db, own["id"]) is not None
    # 別人的仍是 404（與不存在相同），不是 403
    bid = b_appt(client, auth, w)
    assert client.request("DELETE", "/appointments", headers=h, json={"ids": [bid["id"]]}).status_code == 404
    s9, e9 = _slot(9)
    bb = client.post("/appointments/batch", headers=auth(w["b"]), json={
        "case_id": w["case_b"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s9.isoformat(), "end_time": e9.isoformat()}]}).json()[0]["batch_id"]
    assert client.request("DELETE", f"/appointments/batch?batch_id={bb}", headers=h).status_code == 404
    # 取消自己的可以
    assert client.put(f"/appointments/{own['id']}/cancel", headers=h).json()["status"] == "cancelled"


@pytest.mark.parametrize("who", ["staff", "admin"])
def test_staff_and_admin_can_delete(client, auth, world, db, who):
    w = world
    own = post(client, auth, w["a"], w["case_a"], w["room"], day=7).json()
    r = client.request("DELETE", "/appointments", headers=auth(w[who]), json={"ids": [own["id"]]})
    assert r.status_code == 200 and r.json()["deleted"] == 1
