"""階段 4 的 E、F：/rooms/occupancy 與診間主檔維護（is_active、sort_order）。"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.database import engine
from app.models.event import Event
from app.models.room import Room

API_DIR = Path(__file__).resolve().parents[1]
SECRET_EVENT = "秘密講座名稱"


def _slot(days=3, hour=10, hours=1):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=hours)


@pytest.fixture()
def w(make_user, make_case, room, db):
    t1 = make_user("therapist", name="林心理師")
    t2 = make_user("therapist", name="陳心理師")
    staff = make_user("staff")
    admin = make_user("admin")
    c1 = make_case(t1, "王小明", chief_complaint="家暴創傷")
    c2 = make_case(t2, "李小華")
    r2 = Room(name="晤談室 3C", floor=3, room_code="3C")
    db.add(r2)
    db.commit()
    return dict(t1=t1, t2=t2, staff=staff, admin=admin, c1=c1, c2=c2, room=room, r2=r2)


def _book(client, auth, who, case, room, s, e):
    return client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat()})


def _occ(client, auth, who, s, e, **q):
    return client.get("/rooms/occupancy", params={"start": s.isoformat(), "end": e.isoformat(), **q}, headers=auth(who))


# ---- E：/rooms/occupancy ------------------------------------------------------
def test_occupancy_response_has_only_four_fields_and_no_personal_data(client, auth, w, db):
    s, e = _slot()
    assert _book(client, auth, w["staff"], w["c1"], w["room"], s, e).status_code == 201
    db.add(Event(name=SECRET_EVENT, room_id=w["r2"].id, start_at=s, end_at=e,
                 borrower_type="external", borrower_name="外部講師"))
    db.commit()
    for who in ("t1", "t2", "staff", "admin"):
        r = _occ(client, auth, w[who], s - timedelta(days=1), e + timedelta(days=1))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        for row in rows:
            assert set(row) == {"room_id", "start", "end", "occupied"} and row["occupied"] is True
        blob = json.dumps(rows, ensure_ascii=False) + r.text
        for banned in ("王小明", "李小華", "林心理師", "陳心理師", "家暴創傷", SECRET_EVENT, "外部講師",
                       "therapist", "case", "appointment_number"):
            assert banned not in blob


def test_therapist_sees_other_therapists_occupancy_on_calendar(client, auth, w):
    s, e = _slot()
    _book(client, auth, w["staff"], w["c1"], w["room"], s, e)       # 林的場次
    r = _occ(client, auth, w["t2"], s - timedelta(hours=1), e + timedelta(hours=1))  # 陳在看
    assert [x["room_id"] for x in r.json()] == [w["room"].id]
    # 陳自己的 /appointments 仍然看不到
    assert client.get("/appointments", headers=auth(w["t2"])).json() == []


def test_occupancy_only_booked_executed_and_events_with_setup(client, auth, w, db):
    s, e = _slot()
    a = _book(client, auth, w["staff"], w["c1"], w["room"], s, e).json()
    s2, e2 = s + timedelta(hours=3), e + timedelta(hours=3)
    b = _book(client, auth, w["staff"], w["c2"], w["room"], s2, e2).json()
    client.put(f"/appointments/{b['id']}/cancel", headers=auth(w["staff"]))
    db.add(Event(name="講座", room_id=w["r2"].id, start_at=s, end_at=e, setup_start_at=s - timedelta(minutes=45),
                 setup_end_at=s, borrower_type="external", borrower_name="x"))
    db.commit()
    rows = _occ(client, auth, w["t1"], s - timedelta(days=1), e2 + timedelta(days=1)).json()
    by_room = {r["room_id"]: r for r in rows}
    assert len(rows) == 2                         # 取消的不算
    assert datetime.fromisoformat(by_room[w["r2"].id]["start"]) == s - timedelta(minutes=45)  # 含場佈
    assert a["id"]


def test_occupancy_is_not_limited_to_200_rows(client, auth, w, db, make_appt):
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=5)
    for i in range(230):  # 兩間診間輪流、每場一小時不重疊
        make_appt(w["c1"], w["t1"], w["room"] if i % 2 else w["r2"], start=base + timedelta(hours=i), hours=1)
    rows = _occ(client, auth, w["t2"], base - timedelta(days=1), base + timedelta(days=15)).json()
    assert len(rows) == 230
    assert len(client.get("/appointments", headers=auth(w["admin"])).json()) == 200  # 對照：列表仍有上限


def test_occupancy_filter_and_validation(client, auth, w):
    s, e = _slot()
    _book(client, auth, w["staff"], w["c1"], w["room"], s, e)
    assert _occ(client, auth, w["t1"], s - timedelta(hours=1), e + timedelta(hours=1), room_id=w["r2"].id).json() == []
    assert _occ(client, auth, w["t1"], e, s).status_code == 400
    assert _occ(client, auth, w["t1"], s, s + timedelta(days=63)).status_code == 400
    assert client.get("/rooms/occupancy", params={"start": s.isoformat(), "end": e.isoformat()}).status_code in (401, 403)


# ---- F：診間維護 --------------------------------------------------------------
def test_only_admin_can_create_or_update_rooms(client, auth, w):
    body = {"name": "新診間", "floor": 4, "room_code": "4A"}
    for who in ("t1", "staff"):
        assert client.post("/rooms", headers=auth(w[who]), json=body).status_code == 403
        assert client.put(f"/rooms/{w['room'].id}", headers=auth(w[who]), json={"name": "x"}).status_code == 403
    assert client.post("/rooms", json=body).status_code in (401, 403)
    r = client.post("/rooms", headers=auth(w["admin"]), json=body)
    assert r.status_code == 201 and r.json()["is_active"] is True and r.json()["sort_order"] == 0
    r = client.put(f"/rooms/{r.json()['id']}", headers=auth(w["admin"]), json={"name": "改名", "sort_order": 5})
    assert r.status_code == 200 and r.json()["name"] == "改名" and r.json()["sort_order"] == 5


def test_duplicate_room_code_409(client, auth, w):
    assert client.post("/rooms", headers=auth(w["admin"]),
                       json={"name": "x", "floor": 1, "room_code": "2B"}).status_code == 409
    assert client.put(f"/rooms/{w['r2'].id}", headers=auth(w["admin"]), json={"room_code": "2B"}).status_code == 409


def test_no_delete_endpoint(client, auth, w):
    assert client.delete(f"/rooms/{w['room'].id}", headers=auth(w["admin"])).status_code == 405


def test_deactivate_blocked_with_booked_count_then_allowed_after_cancel(client, auth, w):
    s, e = _slot()
    a1 = _book(client, auth, w["staff"], w["c1"], w["room"], s, e).json()
    a2 = _book(client, auth, w["staff"], w["c2"], w["room"], s + timedelta(days=1), e + timedelta(days=1)).json()
    r = client.put(f"/rooms/{w['room'].id}", headers=auth(w["admin"]), json={"is_active": False})
    assert r.status_code == 409 and "2 筆" in r.json()["detail"] and "2B" in r.json()["detail"]
    assert "王小明" not in r.text
    client.put(f"/appointments/{a1['id']}/cancel", headers=auth(w["staff"]))
    r = client.put(f"/rooms/{w['room'].id}", headers=auth(w["admin"]), json={"is_active": False})
    assert r.status_code == 409 and "1 筆" in r.json()["detail"]
    client.put(f"/appointments/{a2['id']}/cancel", headers=auth(w["staff"]))
    assert client.put(f"/rooms/{w['room'].id}", headers=auth(w["admin"]), json={"is_active": False}).status_code == 200


def test_executed_history_does_not_block_deactivation_and_stays_visible(client, auth, w, make_appt):
    appt = make_appt(w["c1"], w["t1"], w["room"], status="executed")
    assert client.put(f"/rooms/{w['room'].id}", headers=auth(w["admin"]), json={"is_active": False}).status_code == 200
    rows = client.get("/appointments", headers=auth(w["admin"])).json()
    assert [x["id"] for x in rows] == [appt.id] and rows[0]["room_id"] == w["room"].id  # 歷史照常顯示


def test_inactive_room_cannot_be_booked_anywhere(client, auth, w):
    client.put(f"/rooms/{w['r2'].id}", headers=auth(w["admin"]), json={"is_active": False})
    s, e = _slot()
    r = _book(client, auth, w["staff"], w["c1"], w["r2"], s, e)
    assert r.status_code == 400 and "3C" in r.json()["detail"] and "停用" in r.json()["detail"]
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["c1"].id, "room_id": w["r2"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s.isoformat(), "end_time": e.isoformat()}]})
    assert r.status_code == 400
    ok = _book(client, auth, w["staff"], w["c1"], w["room"], s, e).json()
    r = client.put(f"/appointments/{ok['id']}", headers=auth(w["staff"]), json={"room_id": w["r2"].id})
    assert r.status_code == 400  # 改房到停用診間也不行
    # 重新啟用後又可以
    client.put(f"/rooms/{w['r2'].id}", headers=auth(w["admin"]), json={"is_active": True})
    assert client.put(f"/appointments/{ok['id']}", headers=auth(w["staff"]), json={"room_id": w["r2"].id}).status_code == 200


def test_inactive_room_hidden_from_list_and_availability(client, auth, w):
    client.put(f"/rooms/{w['r2'].id}", headers=auth(w["admin"]), json={"is_active": False})
    s, e = _slot()
    codes = [x["room_code"] for x in client.get("/rooms", headers=auth(w["t1"])).json()]
    assert codes == ["2B"]
    all_codes = {x["room_code"] for x in client.get("/rooms?include_inactive=true", headers=auth(w["t1"])).json()}
    assert all_codes == {"2B", "3C"}
    av = client.get("/rooms/availability", params={"start": s.isoformat(), "end": e.isoformat()}, headers=auth(w["staff"]))
    assert {x["room_code"] for x in av.json()} == {"2B"}


def test_rooms_ordered_by_sort_order_and_audited(client, auth, w, db):
    client.put(f"/rooms/{w['r2'].id}", headers=auth(w["admin"]), json={"sort_order": -1})
    assert [x["room_code"] for x in client.get("/rooms", headers=auth(w["t1"])).json()] == ["3C", "2B"]
    n = db.execute(text("SELECT count(*) FROM audit_log WHERE table_name = 'rooms'")).scalar()
    assert n == 1


# ---- migration zi9e3f4a5b6e ---------------------------------------------------
def _mig():
    path = API_DIR / "alembic" / "versions" / "zi9e3f4a5b6e_rooms_active_sort.py"
    spec = importlib.util.spec_from_file_location("zi9e3f4a5b6e", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(_mig(), fn)()


def _cols():
    return {c["name"] for c in inspect(engine).get_columns("rooms")}


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_downgrade_then_upgrade_keeps_data(db, w):
    assert {"is_active", "sort_order"} <= _cols()
    db.rollback()
    try:
        _run("downgrade")
        assert not {"is_active", "sort_order"} & _cols()
        assert db.execute(text("SELECT count(*) FROM rooms")).scalar() == 2   # 診間資料沒被動到
        db.rollback()
        _run("upgrade")
        assert {"is_active", "sort_order"} <= _cols()
        rows = db.execute(text("SELECT is_active, sort_order FROM rooms")).fetchall()
        assert all(r[0] is True and r[1] == 0 for r in rows)  # 既有診間預設啟用、排序 0
    finally:
        db.rollback()
        if not {"is_active", "sort_order"} <= _cols():
            _run("upgrade")


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_only_adds_columns_no_drop_table():
    txt = (API_DIR / "alembic" / "versions" / "zi9e3f4a5b6e_rooms_active_sort.py").read_text(encoding="utf-8")
    assert 'down_revision = "zh8d2e3f4a5d"' in txt
    assert "drop_table" not in txt and "DROP TABLE" not in txt.upper() and "DELETE" not in txt.upper()
