"""預約帶方案：建立時由 plan_pricing 算出應收與個案自付額並存成快照。

- 自費：金額必填；自付額＝全額。機構：由方案價目帶出，行政可手動調整（寫稽核）。
- 改方案、價目項目、交通費 → 重新計算；改價目主檔不影響既有預約。
- Google 標題的金額＝個案這次要付的錢（機構＝自付額、自費＝全額，0 不顯示）。
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.appointment import Appointment
from app.models.institution import Institution
from app.services import gcal_titles


def _slot(days=3, hour=10, hours=1):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=hours)


@pytest.fixture()
def world(make_user, make_case, room, db):
    a = make_user("therapist", name="甲心理師")
    b = make_user("therapist", name="乙心理師")
    staff, admin = make_user("staff"), make_user("admin")
    inst_case = make_case(a, "甲的機構案")
    inst_case.funding_source = "institution"
    self_case = make_case(a, "甲的自費案")
    other_case = make_case(b, "乙的機構案")
    other_case.funding_source = "institution"
    inst = Institution(name="某某基金會", code="ABC")
    db.add(inst)
    db.commit()
    return dict(a=a, b=b, staff=staff, admin=admin, inst_case=inst_case, self_case=self_case,
                other_case=other_case, room=room, inst=inst)


def make_plan(client, auth, w, rate_items=None, transport=None):
    c = client.post("/institution-contracts", headers=auth(w["admin"]), json={
        "institution_id": w["inst"].id, "name": "115 合約", "hourly_rate": 1600, "self_pay_amount": 200}).json()
    p = client.post("/institution-plans", headers=auth(w["admin"]), json={
        "contract_id": c["id"], "name": "個別方案", "per_person_count": 10,
        "rate_items": rate_items if rate_items is not None else [
            {"label": "個別 50 分", "total_amount": 1600, "self_pay_amount": 200}],
        "transport_fees": transport if transport is not None else [
            {"label": "市區", "amount": 100, "is_default": True}, {"label": "跨區", "amount": 300}]})
    assert p.status_code == 201, p.text
    return p.json()


def quota(client, auth, w, case, plan, total=10):
    r = client.post(f"/cases/{case.id}/quotas", headers=auth(w["staff"]),
                    json={"institution_id": w["inst"].id, "plan_id": plan["id"], "total_count": total})
    assert r.status_code == 201, r.text
    return r.json()


def book(client, auth, who, case, room, day=3, hour=10, **extra):
    s, e = _slot(day, hour)
    return client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person",
        "start_time": s.isoformat(), "end_time": e.isoformat(), **extra})


def row(db, appt_id):
    db.expire_all()
    return db.get(Appointment, appt_id)


# ---------------------------------------------------------------------------
# 自費：金額必填，自付額＝全額
# ---------------------------------------------------------------------------
def test_self_pay_requires_amount_and_snapshots_full_amount(client, auth, world, db):
    w = world
    assert book(client, auth, w["staff"], w["self_case"], w["room"]).status_code == 422  # 沒填金額
    r = book(client, auth, w["staff"], w["self_case"], w["room"], amount=1800)
    assert r.status_code == 201, r.text
    j = r.json()
    assert (j["funding_source"], j["amount"], j["self_pay_amount"], j["plan_id"]) == ("self_pay", 1800, 1800, None)
    assert float(row(db, j["id"]).self_pay_amount) == 1800
    # 心理師建立自己的自費預約一樣要填
    assert book(client, auth, w["a"], w["self_case"], w["room"], day=4).status_code == 422
    assert book(client, auth, w["a"], w["self_case"], w["room"], day=4, amount=0).status_code == 201  # 免費場次可填 0
    # 自費改金額 → 自付額跟著變
    r = client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"amount": 2000})
    assert r.json()["amount"] == 2000 and r.json()["self_pay_amount"] == 2000


# ---------------------------------------------------------------------------
# 機構：方案帶出應收與自付額、交通費
# ---------------------------------------------------------------------------
def test_institution_price_comes_from_plan_rate_item(client, auth, world, db):
    w = world
    p = make_plan(client, auth, w)
    q = quota(client, auth, w, w["inst_case"], p)
    r = book(client, auth, w["staff"], w["inst_case"], w["room"])  # 沒送金額、方案、價目：全自動
    assert r.status_code == 201, r.text
    j = r.json()
    assert (j["funding_source"], j["quota_id"], j["plan_id"], j["plan_name"]) == ("institution", q["id"], p["id"], "個別方案")
    assert (j["amount"], j["self_pay_amount"], j["transport_fee"]) == (1600, 200, 0)  # 現場無交通費
    assert j["rate_item_label"] == "個別 50 分" and j["rate_item_id"] == p["rate_items"][0]["id"]
    # 外出：用預設交通費；也可指定選項
    s, e = _slot(5)
    out = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["inst_case"].id, "session_type": "outdoor",
        "start_time": s.isoformat(), "end_time": e.isoformat()}).json()
    assert (out["transport_fee"], out["transport_fee_label"]) == (100, "市區")
    far = [t for t in p["transport_fees"] if t["label"] == "跨區"][0]
    s, e = _slot(6)
    out2 = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": w["inst_case"].id, "session_type": "outdoor", "transport_fee_option_id": far["id"],
        "start_time": s.isoformat(), "end_time": e.isoformat()}).json()
    assert out2["transport_fee"] == 300


def test_tiered_rate_items_by_session_number(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "第 1 次", "total_amount": 1600, "self_pay_amount": 0, "session_seq_from": 1, "session_seq_to": 1},
        {"label": "第 2 次起", "total_amount": 1600, "self_pay_amount": 200, "session_seq_from": 2}])
    quota(client, auth, w, w["inst_case"], p)
    first = book(client, auth, w["staff"], w["inst_case"], w["room"], day=3).json()
    second = book(client, auth, w["staff"], w["inst_case"], w["room"], day=4).json()
    assert (first["rate_item_label"], first["self_pay_amount"]) == ("第 1 次", 0)
    assert (second["rate_item_label"], second["self_pay_amount"]) == ("第 2 次起", 200)


def test_batch_uses_plan_for_every_slot(client, auth, world):
    w = world
    p = make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p)
    slots = [{"start_time": _slot(d)[0].isoformat(), "end_time": _slot(d)[1].isoformat()} for d in (3, 4)]
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["inst_case"].id, "room_id": w["room"].id, "session_type": "in_person", "slots": slots})
    assert r.status_code == 201, r.text
    assert [(x["amount"], x["self_pay_amount"]) for x in r.json()] == [(1600, 200), (1600, 200)]


def test_institution_without_plan_warns_and_allows_manual_amount(client, auth, world):
    w = world
    r = book(client, auth, w["staff"], w["inst_case"], w["room"], amount=900)
    assert r.status_code == 201
    assert r.json()["amount"] == 900 and r.json()["self_pay_amount"] == 0 and r.json()["warnings"]


def test_plan_and_rate_item_must_belong_together(client, auth, world):
    w = world
    p1, p2 = make_plan(client, auth, w), make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p1)
    r = book(client, auth, w["staff"], w["inst_case"], w["room"], rate_item_id=p2["rate_items"][0]["id"])
    assert r.status_code == 400
    r = book(client, auth, w["staff"], w["inst_case"], w["room"], transport_fee_option_id=p2["transport_fees"][0]["id"])
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 手動調整（稽核）、重新計算、主檔變更不影響既有預約
# ---------------------------------------------------------------------------
def audits(db, appt_id):
    return db.execute(text("SELECT before_data, after_data FROM audit_log WHERE table_name='appointments' AND record_id=:i ORDER BY id"),
                      {"i": appt_id}).all()


def test_manual_adjustment_on_institution_is_audited(client, auth, world, db):
    w = world
    p = make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p)
    j = book(client, auth, w["staff"], w["inst_case"], w["room"]).json()
    r = client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"amount": 1400})
    assert r.status_code == 200 and (r.json()["amount"], r.json()["self_pay_amount"]) == (1400, 200)
    manual = [a for a in audits(db, j["id"]) if (a.after_data or {}).get("manual")]
    assert manual and manual[-1].before_data["amount"] == 1600 and manual[-1].after_data["amount"] == 1400
    # 建立時就手動指定金額也要留稽核
    j2 = book(client, auth, w["staff"], w["inst_case"], w["room"], day=4, amount=1000).json()
    assert j2["amount"] == 1000 and any((a.after_data or {}).get("manual") for a in audits(db, j2["id"]))


def test_changing_plan_rate_item_or_transport_recalculates(client, auth, world):
    w = world
    p1 = make_plan(client, auth, w, rate_items=[
        {"label": "個別", "total_amount": 1600, "self_pay_amount": 200},
        {"label": "家族", "total_amount": 2000, "self_pay_amount": 300}])
    quota(client, auth, w, w["inst_case"], p1)
    j = book(client, auth, w["staff"], w["inst_case"], w["room"]).json()
    family = [r for r in p1["rate_items"] if r["label"] == "家族"][0]
    r = client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"rate_item_id": family["id"]})
    assert (r.json()["amount"], r.json()["self_pay_amount"], r.json()["rate_item_label"]) == (2000, 300, "家族")
    far = [t for t in p1["transport_fees"] if t["label"] == "跨區"][0]
    r = client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"transport_fee_option_id": far["id"]})
    assert r.json()["transport_fee"] == 300 and r.json()["amount"] == 2000  # 只改交通費，價目項目沿用
    # 換方案 → 依新方案重算
    p2 = make_plan(client, auth, w, rate_items=[{"label": "新方案", "total_amount": 1000, "self_pay_amount": 100}])
    r = client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"plan_id": p2["id"]})
    assert (r.json()["plan_id"], r.json()["amount"], r.json()["self_pay_amount"]) == (p2["id"], 1000, 100)


def test_editing_plan_master_does_not_change_existing_appointments(client, auth, world, db):
    w = world
    p = make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p)
    old = book(client, auth, w["staff"], w["inst_case"], w["room"], day=3).json()
    body = {"contract_id": p["contract_id"], "name": "個別方案", "per_person_count": 10,
            "rate_items": [{"label": "調價後", "total_amount": 2400, "self_pay_amount": 400}], "transport_fees": []}
    assert client.put(f"/institution-plans/{p['id']}", headers=auth(w["admin"]), json=body).status_code == 200
    kept = row(db, old["id"])
    assert (float(kept.amount), float(kept.self_pay_amount)) == (1600, 200)  # 快照不變
    new = book(client, auth, w["staff"], w["inst_case"], w["room"], day=4).json()
    assert (new["amount"], new["self_pay_amount"]) == (2400, 400)  # 新預約用新價


# ---------------------------------------------------------------------------
# Google 標題的金額＝個案這次要付的錢
# ---------------------------------------------------------------------------
def test_title_amount_is_what_the_client_pays(client, auth, world, db):
    w = world
    p = make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p)
    inst = book(client, auth, w["staff"], w["inst_case"], w["room"], day=3).json()
    selfpay = book(client, auth, w["staff"], w["self_case"], w["room"], day=4, amount=1800).json()
    free = book(client, auth, w["staff"], w["self_case"], w["room"], day=5, amount=0).json()
    t_inst = gcal_titles.event_title(row(db, inst["id"]), "type_room")
    t_self = gcal_titles.event_title(row(db, selfpay["id"]), "type_room")
    t_free = gcal_titles.event_title(row(db, free["id"]), "type_room")
    assert t_inst.endswith("$200") and "1,600" not in t_inst  # 機構案＝自付額，不是應收
    assert t_self.endswith("$1,800")  # 自費案＝全額
    assert "$" not in t_free  # 0 元不顯示
    # 機構案自付額 0（例如第 1 次免費）也不顯示
    p0 = make_plan(client, auth, w, rate_items=[{"label": "免費", "total_amount": 1600, "self_pay_amount": 0}])
    case0 = w["other_case"]
    case0.therapist_id = w["a"].id
    db.commit()
    quota(client, auth, w, case0, p0)
    z = book(client, auth, w["staff"], case0, w["room"], day=6).json()
    assert "$" not in gcal_titles.event_title(row(db, z["id"]), "type_room")


# ---------------------------------------------------------------------------
# 心理師：只看得到自己個案的方案資訊，隔離規則不變
# ---------------------------------------------------------------------------
def test_therapist_sees_own_pricing_only(client, auth, world):
    w = world
    p = make_plan(client, auth, w)
    quota(client, auth, w, w["inst_case"], p)
    quota(client, auth, w, w["other_case"], p)
    mine = book(client, auth, w["a"], w["inst_case"], w["room"], day=3).json()
    assert (mine["amount"], mine["self_pay_amount"], mine["plan_name"]) == (1600, 200, "個別方案")
    theirs = book(client, auth, w["staff"], w["other_case"], w["room"], day=4).json()
    assert client.get(f"/appointments/{theirs['id']}", headers=auth(w["a"])).status_code == 404
    opts = client.get(f"/cases/{w['inst_case'].id}/billing-options", headers=auth(w["a"]))
    assert opts.status_code == 200 and opts.json()["plans"][0]["rate_items"][0]["self_pay_amount"] == 200
    other = client.get(f"/cases/{w['other_case'].id}/billing-options", headers=auth(w["a"]))
    ghost = client.get("/cases/999999/billing-options", headers=auth(w["a"]))
    assert other.status_code == 404 and other.json() == ghost.json()
    # 心理師不能自己改別人的預約的方案
    assert client.put(f"/appointments/{theirs['id']}", headers=auth(w["a"]), json={"plan_id": p["id"]}).status_code == 404


def test_pricing_change_triggers_google_resync(client, auth, world, db):
    """改價目項目（自付額變了）→ 預約入列重新同步，標題的金額跟著變。"""
    from app.models.gcal import GcalOutbox, GoogleOAuthConnection
    from app.services import google_oauth

    db.add(GoogleOAuthConnection(id=1, google_email="owner@example.com", status="active", refresh_token_enc="x",
                                 scopes=" ".join(google_oauth.CALENDAR_SCOPES)))
    db.commit()
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "A", "total_amount": 1600, "self_pay_amount": 200},
        {"label": "B", "total_amount": 1600, "self_pay_amount": 500}])
    quota(client, auth, w, w["inst_case"], p)
    j = book(client, auth, w["staff"], w["inst_case"], w["room"]).json()
    db.query(GcalOutbox).delete()
    db.commit()
    b = [r for r in p["rate_items"] if r["label"] == "B"][0]
    client.put(f"/appointments/{j['id']}", headers=auth(w["staff"]), json={"rate_item_id": b["id"]})
    db.expire_all()
    jobs = db.query(GcalOutbox).filter(GcalOutbox.appointment_id == j["id"]).all()
    assert len(jobs) == 1 and jobs[0].job_type == "upsert_event"
