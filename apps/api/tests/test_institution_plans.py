"""機構方案屬「金流資訊」，已恢復：機構、合約、方案、價目、交通費、個案額度。

核銷批次、對帳、流水帳冊、月結等記帳功能仍是移除狀態（見 test_accounting_writes_gone.py）。
額度規則：只顯示總堂數、已用、剩餘，不擋預約；額度不足只回 warnings。
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.institution import Institution


def _slot(days=3, hour=10, hours=1):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=hours)


@pytest.fixture()
def world(make_user, make_case, room, db):
    a = make_user("therapist", name="甲心理師")
    b = make_user("therapist", name="乙心理師")
    staff, admin = make_user("staff"), make_user("admin")
    case_a = make_case(a, "甲的機構案")
    case_b = make_case(b, "乙的機構案")
    for c in (case_a, case_b):
        c.funding_source = "institution"
    inst = Institution(name="某某基金會", code="ABC")
    db.add(inst)
    db.commit()
    return dict(a=a, b=b, staff=staff, admin=admin, case_a=case_a, case_b=case_b, room=room, inst=inst)


def contract_body(inst, **kw):
    return {"institution_id": inst.id, "name": "115 年諮商合約", "hourly_rate": 1600, "self_pay_amount": 200, **kw}


def plan_body(contract_id, **kw):
    return {"contract_id": contract_id, "name": "個別諮商方案", "per_person_count": 6,
            "rate_items": [{"label": "個別 50 分", "total_amount": 1600, "self_pay_amount": 200}],
            "transport_fees": [{"label": "市區", "amount": 100, "is_default": True}], **kw}


def make_plan(client, auth, w, who="admin"):
    c = client.post("/institution-contracts", json=contract_body(w["inst"]), headers=auth(w[who]))
    assert c.status_code == 201, c.text
    p = client.post("/institution-plans", json=plan_body(c.json()["id"]), headers=auth(w[who]))
    assert p.status_code == 201, p.text
    return c.json(), p.json()


def make_quota(client, auth, w, case, total=2, plan_id=None, **kw):
    r = client.post(f"/cases/{case.id}/quotas", headers=auth(w["staff"]),
                    json={"institution_id": w["inst"].id, "total_count": total, "plan_id": plan_id, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def book(client, auth, who, case, room, day=3, hour=10, **extra):
    s, e = _slot(day, hour)
    return client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person",
        "start_time": s.isoformat(), "end_time": e.isoformat(), **extra})


def quota_row(db, qid):
    db.expire_all()
    return db.get(CaseInstitutionQuota, qid)


# ---------------------------------------------------------------------------
# 管理頁的 API：合約、方案、價目、交通費
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["admin", "staff"])
def test_contracts_plans_rates_and_transport_are_manageable(client, auth, world, who):
    w = world
    c, p = make_plan(client, auth, w, who)
    assert p["rate_items"][0]["total_amount"] == 1600 and p["rate_items"][0]["self_pay_amount"] == 200
    assert p["transport_fees"][0]["amount"] == 100
    # 改價目、停用方案
    body = plan_body(c["id"], name="個別諮商方案（改）",
                     rate_items=[{"label": "個別 50 分", "total_amount": 1800, "self_pay_amount": 300}])
    r = client.put(f"/institution-plans/{p['id']}", json=body, headers=auth(w[who]))
    assert r.status_code == 200 and r.json()["rate_items"][0]["total_amount"] == 1800
    assert client.put(f"/institution-plans/{p['id']}/status?value=expired", headers=auth(w[who])).status_code == 200
    assert client.put(f"/institution-contracts/{c['id']}", json=contract_body(w["inst"], name="改名"), headers=auth(w[who])).status_code == 200


def test_therapist_cannot_manage_or_browse_contracts_and_plans(client, auth, world):
    w = world
    c, p = make_plan(client, auth, w)
    h = auth(w["a"])
    assert client.post("/institution-contracts", json=contract_body(w["inst"]), headers=h).status_code == 403
    assert client.put(f"/institution-plans/{p['id']}", json=plan_body(c["id"]), headers=h).status_code == 403
    assert client.get("/institution-contracts", headers=h).status_code == 403  # 合約價目是診所內部資料
    assert client.get("/institution-plans", headers=h).status_code == 403


# ---------------------------------------------------------------------------
# 個案額度：管理、顯示、隔離
# ---------------------------------------------------------------------------
def test_quota_crud_and_summary(client, auth, world, db):
    w = world
    _, p = make_plan(client, auth, w)
    q = make_quota(client, auth, w, w["case_a"], total=5, plan_id=p["id"])
    assert (q["total_count"], q["used_count"], q["remaining"], q["plan_name"]) == (5, 0, 5, "個別諮商方案")
    r = client.put(f"/quotas/{q['id']}", headers=auth(w["staff"]), json={"total_count": 8})
    assert r.status_code == 200 and r.json()["total_count"] == 8
    # 方案必須屬於該機構
    other = Institution(name="另一機構", code="XYZ")
    db.add(other)
    db.commit()
    bad = client.post(f"/cases/{w['case_a'].id}/quotas", headers=auth(w["staff"]),
                      json={"institution_id": other.id, "total_count": 2, "plan_id": p["id"]})
    assert bad.status_code == 400
    assert client.delete(f"/quotas/{q['id']}", headers=auth(w["admin"])).status_code == 204


def test_therapist_sees_only_own_cases_quotas(client, auth, world):
    w = world
    qa = make_quota(client, auth, w, w["case_a"])
    qb = make_quota(client, auth, w, w["case_b"])
    h = auth(w["a"])
    assert [x["id"] for x in client.get("/quotas", headers=h).json()] == [qa["id"]]
    assert client.get(f"/cases/{w['case_a'].id}/quotas", headers=h).status_code == 200
    other = client.get(f"/cases/{w['case_b'].id}/quotas", headers=h)
    ghost = client.get("/cases/999999/quotas", headers=h)
    assert other.status_code == 404 and other.json() == ghost.json()
    assert qb["id"] not in {x["id"] for x in client.get("/quotas", headers=h).json()}
    # 心理師不能自己加額度、改額度
    assert client.post(f"/cases/{w['case_a'].id}/quotas", headers=h,
                       json={"institution_id": w["inst"].id, "total_count": 3}).status_code == 403
    assert client.put(f"/quotas/{qa['id']}", headers=h, json={"total_count": 99}).status_code == 403


# ---------------------------------------------------------------------------
# 額度流轉：預約、取消、未到、報到；額度不足只警告、不擋
# ---------------------------------------------------------------------------
def test_quota_flow_book_cancel_absent_arrive(client, auth, world, db):
    w = world
    q = make_quota(client, auth, w, w["case_a"], total=3)
    qid = q["id"]
    a1 = book(client, auth, w["staff"], w["case_a"], w["room"], day=3)
    assert a1.status_code == 201, a1.text
    j = a1.json()
    assert j["funding_source"] == "institution" and j["quota_id"] == qid and j["warnings"] == []
    assert (j["quota_used"], j["quota_total"], j["quota_remaining"]) == (0, 3, 2)
    row = quota_row(db, qid)
    assert (row.used_count, row.booked_count, row.reserved_count) == (0, 1, 2)
    # 取消 → 退回
    assert client.put(f"/appointments/{j['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    row = quota_row(db, qid)
    assert (row.used_count, row.booked_count, row.reserved_count) == (0, 0, 3)
    # 未到 → 退回；報到 → 已使用
    a2 = book(client, auth, w["staff"], w["case_a"], w["room"], day=4).json()
    a3 = book(client, auth, w["staff"], w["case_a"], w["room"], day=5).json()
    assert client.put(f"/appointments/{a2['id']}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice"}).status_code == 200
    assert client.put(f"/appointments/{a3['id']}/arrive", headers=auth(w["staff"])).status_code == 200
    row = quota_row(db, qid)
    assert (row.used_count, row.booked_count, row.reserved_count) == (1, 0, 2)
    assert db.execute(text("SELECT count(*) FROM session_records")).scalar() == 0  # 不產生流水


def test_insufficient_quota_creates_with_warning_and_does_not_block(client, auth, world, db):
    w = world
    q = make_quota(client, auth, w, w["case_a"], total=1)
    first = book(client, auth, w["staff"], w["case_a"], w["room"], day=3).json()
    assert first["quota_id"] == q["id"] and first["warnings"] == []
    over = book(client, auth, w["staff"], w["case_a"], w["room"], day=4)
    assert over.status_code == 201, over.text  # 不擋
    assert over.json()["quota_id"] is None and over.json()["warnings"]
    assert over.json()["funding_source"] == "institution"
    row = quota_row(db, q["id"])
    assert (row.used_count, row.booked_count, row.reserved_count) == (0, 1, 0)  # 恆等式維持，沒有被扣成負數
    # 取消沒佔額度的那場，不會動到額度
    assert client.put(f"/appointments/{over.json()['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    assert quota_row(db, q["id"]).booked_count == 1


def test_no_quota_at_all_only_warns(client, auth, world):
    w = world
    r = book(client, auth, w["staff"], w["case_a"], w["room"])
    assert r.status_code == 201 and r.json()["warnings"] and r.json()["quota_id"] is None


def test_batch_booking_over_quota_warns_per_slot_but_books_all(client, auth, world, db):
    w = world
    q = make_quota(client, auth, w, w["case_a"], total=2)
    slots = [{"start_time": _slot(d)[0].isoformat(), "end_time": _slot(d)[1].isoformat()} for d in (3, 4, 5)]
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["case_a"].id, "room_id": w["room"].id, "session_type": "in_person", "slots": slots})
    assert r.status_code == 201, r.text
    rows = r.json()
    assert [bool(x["warnings"]) for x in rows] == [False, False, True]
    assert [x["quota_id"] for x in rows] == [q["id"], q["id"], None]
    row = quota_row(db, q["id"])
    assert (row.booked_count, row.reserved_count) == (2, 0)


def test_change_payment_method_moves_quota(client, auth, world, db):
    w = world
    q = make_quota(client, auth, w, w["case_a"], total=2)
    a = book(client, auth, w["staff"], w["case_a"], w["room"]).json()
    r = client.put(f"/appointments/{a['id']}/payment", headers=auth(w["staff"]), json={"funding_source": "self_pay"})
    assert r.status_code == 200 and r.json()["quota_id"] is None
    assert quota_row(db, q["id"]).reserved_count == 2  # 退回
    r = client.put(f"/appointments/{a['id']}/payment", headers=auth(w["staff"]), json={"funding_source": "institution"})
    assert r.json()["quota_id"] == q["id"] and quota_row(db, q["id"]).booked_count == 1


def test_close_case_zeroes_quota_keeping_history(client, auth, world, db):
    w = world
    q = make_quota(client, auth, w, w["case_a"], total=4)
    a = book(client, auth, w["staff"], w["case_a"], w["room"], day=3).json()
    client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"]))
    book(client, auth, w["staff"], w["case_a"], w["room"], day=5)
    from app.auth.password import hash_password
    w["staff"].password_hash = hash_password("pw123456")
    db.commit()
    r = client.post(f"/cases/{w['case_a'].id}/close", headers=auth(w["staff"]), json={"password": "pw123456", "reason": "結案"})
    assert r.status_code == 200, r.text
    row = quota_row(db, q["id"])
    assert (row.total_count, row.used_count, row.booked_count, row.reserved_count, row.status) == (1, 1, 0, 0, "closed")


# ---------------------------------------------------------------------------
# 心理師：只看得到自己個案的額度資訊；他人預約一律 404
# ---------------------------------------------------------------------------
def test_therapist_sees_own_quota_info_only(client, auth, world):
    w = world
    make_quota(client, auth, w, w["case_a"], total=3)
    make_quota(client, auth, w, w["case_b"], total=7)
    ma = book(client, auth, w["a"], w["case_a"], w["room"], day=3).json()
    mb = book(client, auth, w["staff"], w["case_b"], w["room"], day=4).json()
    assert (ma["quota_total"], ma["quota_remaining"]) == (3, 2)
    assert client.get(f"/appointments/{mb['id']}", headers=auth(w["a"])).status_code == 404
    listing = client.get("/appointments", headers=auth(w["a"])).json()
    assert [x["id"] for x in listing] == [ma["id"]] and "7" not in str([x["quota_total"] for x in listing])
    today = client.get(f"/me/today?day={_slot(3)[0].date()}", headers=auth(w["a"])).json()
    assert [s["quota"]["total"] for s in today["schedule"] if s["quota"]] == [3]
