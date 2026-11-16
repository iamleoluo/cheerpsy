"""計價正確性：consult_type／service_type 真的帶入價目挑選；第幾次依預約日期排序；
改時長（或日期）時未手動調整的金額重新計價並回 warnings；即時預覽與建立預約同一套計價。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.institution import Institution
from tests.test_appointment_pricing import make_plan, quota


def _t(days, hour=10, minutes=60):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(minutes=minutes)


@pytest.fixture()
def world(make_user, make_case, room, db):
    a, admin, staff = make_user("therapist", name="甲"), make_user("admin"), make_user("staff")
    c = make_case(a, "機構案")
    c.funding_source = "institution"
    couple = make_case(a, "伴侶案")
    couple.funding_source = "institution"
    couple.case_type = "couple"
    inst = Institution(name="基金會", code="CC")
    db.add(inst)
    db.commit()
    return dict(a=a, admin=admin, staff=staff, c=c, couple=couple, room=room, inst=inst)


def book(client, auth, w, case, day, minutes=60, hour=10, **extra):
    s, e = _t(day, hour, minutes)
    return client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": case.id, "room_id": w["room"].id, "session_type": "in_person",
        "start_time": s.isoformat(), "end_time": e.isoformat(), **extra})


ITEMS = [
    {"label": "個別", "total_amount": 1600, "self_pay_amount": 200, "consult_type": "individual"},
    {"label": "伴侶", "total_amount": 2400, "self_pay_amount": 300, "consult_type": "couple"},
    {"label": "親職", "total_amount": 1000, "self_pay_amount": 100, "consult_type": "parenting"},
]


def test_consult_type_is_used_to_pick_the_rate_item(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=ITEMS)
    quota(client, auth, w, w["c"], p)
    quota(client, auth, w, w["couple"], p)
    ind = book(client, auth, w, w["c"], 3).json()
    assert (ind["consult_type"], ind["rate_item_label"], ind["amount"]) == ("individual", "個別", 1600)
    par = book(client, auth, w, w["c"], 4, consult_type="parenting").json()
    assert (par["rate_item_label"], par["amount"], par["self_pay_amount"]) == ("親職", 1000, 100)
    cp = book(client, auth, w, w["couple"], 5).json()  # 伴侶案預設 couple
    assert (cp["consult_type"], cp["rate_item_label"], cp["amount"]) == ("couple", "伴侶", 2400)
    assert book(client, auth, w, w["c"], 6, consult_type="group").status_code == 422
    # 沒有符合諮商型態的價目 → 不亂套別的價目：家族沒有價目，退回合約鐘點費並警告
    fam = book(client, auth, w, w["c"], 7, consult_type="family").json()
    assert fam["rate_item_label"] is None and fam["warnings"]


def test_service_type_is_used_and_unspecified_does_not_match_typed_items(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "會面交往", "total_amount": 800, "self_pay_amount": 0, "service_type": "visitation"},
        {"label": "一般", "total_amount": 1600, "self_pay_amount": 200}])
    quota(client, auth, w, w["c"], p)
    plain = book(client, auth, w, w["c"], 3).json()
    assert (plain["rate_item_label"], plain["amount"]) == ("一般", 1600)  # 沒指定服務型態不會套到會面交往
    vis = book(client, auth, w, w["c"], 4, service_type="visitation").json()
    assert (vis["service_type"], vis["rate_item_label"], vis["amount"]) == ("visitation", "會面交往", 800)


def test_session_number_follows_appointment_date_not_creation_order(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "第 1 次", "total_amount": 1600, "self_pay_amount": 0, "session_seq_from": 1, "session_seq_to": 1},
        {"label": "第 2 次起", "total_amount": 1600, "self_pay_amount": 200, "session_seq_from": 2}])
    quota(client, auth, w, w["c"], p)
    late = book(client, auth, w, w["c"], 10).json()  # 先建立較晚的日期
    early = book(client, auth, w, w["c"], 3).json()  # 後建立但日期較早 → 才是第 1 次
    assert late["rate_item_label"] == "第 1 次"  # 建立當下它確實是唯一一筆（快照，不回頭改）
    assert early["rate_item_label"] == "第 1 次"  # 依日期它是第 1 次（舊算法會變成第 2 次）
    third = book(client, auth, w, w["c"], 6).json()  # 夾在中間 → 第 2 次（前面只有 early）
    assert third["rate_item_label"] == "第 2 次起"


def test_changing_duration_reprices_untouched_amounts_and_warns(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "50 分", "total_amount": 1600, "self_pay_amount": 200, "duration_minutes": 50},
        {"label": "80 分", "total_amount": 2400, "self_pay_amount": 300, "duration_minutes": 80}])
    quota(client, auth, w, w["c"], p)
    a = book(client, auth, w, w["c"], 3, minutes=50).json()
    assert (a["rate_item_label"], a["amount"]) == ("50 分", 1600)
    s, e = _t(3, 10, 80)
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["rate_item_label"], j["amount"], j["self_pay_amount"]) == ("80 分", 2400, 300)
    assert j["warnings"] and "重新計價" in j["warnings"][0]
    # 沒改到價（時間不變、只換診間）→ 沒有警告
    again = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"room_id": w["room"].id}).json()
    assert again["warnings"] == [] and again["amount"] == 2400


def test_manually_adjusted_amount_is_not_overwritten_when_duration_changes(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "50 分", "total_amount": 1600, "self_pay_amount": 200, "duration_minutes": 50},
        {"label": "80 分", "total_amount": 2400, "self_pay_amount": 300, "duration_minutes": 80}])
    quota(client, auth, w, w["c"], p)
    a = book(client, auth, w, w["c"], 3, minutes=50).json()
    client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"amount": 1500})  # 行政手動調整
    s, e = _t(3, 10, 80)
    j = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()}).json()
    assert j["amount"] == 1500 and j["rate_item_label"] == "50 分"  # 沒被蓋掉
    assert j["warnings"] and "手動" in j["warnings"][0]


def test_explicit_rate_item_is_not_overwritten_when_duration_changes(client, auth, world):
    w = world
    p = make_plan(client, auth, w, rate_items=[
        {"label": "50 分", "total_amount": 1600, "self_pay_amount": 200, "duration_minutes": 50},
        {"label": "特約", "total_amount": 1200, "self_pay_amount": 0}])
    quota(client, auth, w, w["c"], p)
    special = [r for r in p["rate_items"] if r["label"] == "特約"][0]
    a = book(client, auth, w, w["c"], 3, minutes=50, rate_item_id=special["id"]).json()
    s, e = _t(3, 10, 80)
    j = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()}).json()
    assert (j["rate_item_label"], j["amount"]) == ("特約", 1200) and j["warnings"]


def test_self_pay_is_not_repriced_on_time_change(client, auth, world, make_case):
    w = world
    sp = make_case(w["a"], "自費")
    a = book(client, auth, w, sp, 3, minutes=50, amount=1800).json()
    s, e = _t(3, 10, 80)
    j = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()}).json()
    assert j["amount"] == 1800 and j["warnings"] == []


def test_pricing_preview_matches_creation_and_is_isolated(client, auth, world, make_user):
    w = world
    p = make_plan(client, auth, w, rate_items=ITEMS)
    quota(client, auth, w, w["c"], p)
    day = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()
    pv = client.get(f"/cases/{w['c'].id}/pricing-preview", headers=auth(w["a"]),
                    params={"on_date": day, "duration_minutes": 60, "consult_type": "parenting"}).json()
    assert pv["error"] is None and (pv["rate_item_label"], pv["amount"], pv["institution_subsidy"]) == ("親職", 1000, 900)
    made = book(client, auth, w, w["c"], 3, consult_type="parenting").json()
    assert (made["amount"], made["self_pay_amount"]) == (pv["amount"], pv["self_pay_amount"])
    other = make_user("therapist", name="乙")
    assert client.get(f"/cases/{w['c'].id}/pricing-preview", headers=auth(other), params={"on_date": day}).status_code == 404
