"""診間預約（階段 4 的 A～D）：資料庫層保證不重疊、未到／取消釋出、空房查詢、行政改期改房。

重點：
- 重疊由資料庫的 exclusion constraint（ex_appointments_room）保證，不只靠應用層先查再寫。
- 只有 booked／executed 佔用診間；cancelled、no_show 釋出。
- 並行測試用「真的獨立的資料庫連線」，不是同一個 session。
- 409 訊息只寫診間代號與時段，不帶個案、心理師或活動名稱。
"""

import importlib.util
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import engine
from app.models.event import Event
from app.models.room import Room

API_DIR = Path(__file__).resolve().parents[1]
CONSTRAINT = "ex_appointments_room"
TZ8 = timezone(timedelta(hours=8))


def _slot(days=3, hour=10, hours=1):
    start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    return start, start + timedelta(hours=hours)


@pytest.fixture()
def w(make_user, make_case, room, db):
    t = make_user("therapist", name="林心理師")
    t2 = make_user("therapist", name="陳心理師")
    staff = make_user("staff")
    admin = make_user("admin")
    case = make_case(t, "王小明")
    case2 = make_case(t2, "李小華")
    room2 = Room(name="晤談室 3C", floor=3, room_code="3C")
    play = Room(name="遊戲室 2C", floor=2, room_code="2C", room_type="play")
    db.add_all([room2, play])
    db.commit()
    return dict(t=t, t2=t2, staff=staff, admin=admin, case=case, case2=case2,
                room=room, room2=room2, play=play)


def _create(client, auth, who, case, room, start, end, **extra):
    body = {"case_id": case.id, "room_id": room.id if room else None, "session_type": "in_person", "amount": 1000,
            "start_time": start.isoformat(), "end_time": end.isoformat(), **extra}
    return client.post("/appointments", json=body, headers=auth(who))


def _sql_insert(conn, n, therapist_id, room_id, s, e, status="booked"):
    return conn.execute(text(
        "INSERT INTO appointments (appointment_number, therapist_id, room_id, session_type, "
        "time_range, amount, status) VALUES (:n, :t, :r, 'in_person', tstzrange(:s, :e), 0, :st)"),
        {"n": n, "t": therapist_id, "r": room_id, "s": s, "e": e, "st": status})


def _has_constraint(db) -> bool:
    return db.execute(text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": CONSTRAINT}).first() is not None


# ---- 資料庫層：繞過 API 直接寫也會被擋 ---------------------------------------
def test_constraint_exists(db):
    assert _has_constraint(db)


def test_db_rejects_overlap_even_bypassing_api(db, w):
    s, e = _slot()
    _sql_insert(db, "X-1", w["t"].id, w["room"].id, s, e)
    db.commit()
    with pytest.raises(IntegrityError) as exc:
        _sql_insert(db, "X-2", w["t2"].id, w["room"].id, s + timedelta(minutes=30), e + timedelta(minutes=30))
    assert exc.value.orig.pgcode == "23P01"
    db.rollback()


def test_db_allows_adjacent_other_room_and_no_room(db, w):
    s, e = _slot()
    _sql_insert(db, "Y-1", w["t"].id, w["room"].id, s, e)
    _sql_insert(db, "Y-2", w["t2"].id, w["room"].id, e, e + timedelta(hours=1))        # 緊接著
    _sql_insert(db, "Y-3", w["t2"].id, w["room2"].id, s, e)                            # 另一間
    _sql_insert(db, "Y-4", w["t"].id, None, s, e)                                      # 線上沒有診間
    _sql_insert(db, "Y-5", w["t2"].id, None, s, e)
    db.commit()


@pytest.mark.parametrize("released", ["cancelled", "no_show"])
def test_db_released_statuses_do_not_occupy(db, w, released):
    s, e = _slot()
    _sql_insert(db, "Z-1", w["t"].id, w["room"].id, s, e, status=released)
    _sql_insert(db, "Z-2", w["t2"].id, w["room"].id, s, e, status="booked")   # 可以再約
    db.commit()
    # 把釋出的場次改回 booked 就會撞到
    with pytest.raises(IntegrityError) as exc:
        db.execute(text("UPDATE appointments SET status = 'booked' WHERE appointment_number = 'Z-1'"))
    assert exc.value.orig.pgcode == "23P01"
    db.rollback()


# ---- 並行：兩條真的獨立連線 ---------------------------------------------------
@pytest.mark.real_commit
def test_two_connections_race_second_waits_then_fails(w):
    s, e = _slot()
    ins_args = lambda n, t: (n, t, w["room"].id, s, e)  # noqa: E731
    c1 = engine.connect()
    t1 = c1.begin()
    _sql_insert(c1, "R-1", w["t"].id, w["room"].id, s, e)      # 連線 1：寫入但還沒 commit

    result: dict = {}

    def second():
        with engine.connect() as c2:
            try:
                with c2.begin():
                    _sql_insert(c2, "R-2", w["t2"].id, w["room"].id, s, e)
                result["ok"] = True
            except IntegrityError as exc:
                result["pgcode"] = exc.orig.pgcode

    th = threading.Thread(target=second)
    th.start()
    time.sleep(0.6)
    assert th.is_alive(), "連線 2 應該卡在等連線 1 的結果，而不是直接成功"
    t1.commit()
    c1.close()
    th.join(10)
    assert not th.is_alive()
    assert result == {"pgcode": "23P01"}, result
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM appointments WHERE room_id = :r"),
                         {"r": w["room"].id}).scalar() == 1


@pytest.mark.real_commit
def test_two_connections_first_rolls_back_second_succeeds(w):
    s, e = _slot()
    c1 = engine.connect()
    t1 = c1.begin()
    _sql_insert(c1, "RB-1", w["t"].id, w["room"].id, s, e)
    result: dict = {}

    def second():
        with engine.connect() as c2:
            try:
                with c2.begin():
                    _sql_insert(c2, "RB-2", w["t2"].id, w["room"].id, s, e)
                result["ok"] = True
            except IntegrityError as exc:
                result["pgcode"] = exc.orig.pgcode

    th = threading.Thread(target=second)
    th.start()
    time.sleep(0.6)
    assert th.is_alive()
    t1.rollback()
    c1.close()
    th.join(10)
    assert result == {"ok": True}


@pytest.mark.real_commit
def test_api_race_many_clients_exactly_one_wins(client, auth, w, db):
    """同一時段同時送出 6 個建立預約：恰好 1 個 201，其餘 409，資料庫只有 1 筆。"""
    from fastapi.testclient import TestClient
    from app.main import app

    s, e = _slot(hour=14)
    n = 6
    barrier = threading.Barrier(n, timeout=30)
    headers = auth(w["staff"])
    body = {"case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
            "start_time": s.isoformat(), "end_time": e.isoformat()}

    def go(_):
        c = TestClient(app)
        barrier.wait()
        return c.post("/appointments", json=body, headers=headers)

    with ThreadPoolExecutor(n) as ex:
        responses = list(ex.map(go, range(n)))
    codes = sorted(r.status_code for r in responses)
    assert codes == [201] + [409] * (n - 1), [(r.status_code, r.text[:120]) for r in responses]
    for r in responses:
        if r.status_code == 409:
            # 診間約束擋下講 2B；若對方已 commit 而被心理師／個案檢查先擋下，則只講時段。兩者都不帶姓名
            assert "2B" in r.json()["detail"] or "已有其他預約" in r.json()["detail"]
            assert "王小明" not in r.text and "林心理師" not in r.text
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM appointments WHERE room_id = :r"),
                      {"r": w["room"].id}).scalar() == 1


def test_constraint_violation_is_409_with_room_and_time_not_500(client, auth, w, monkeypatch):
    """應用層檢查被繞過（模擬 race）時，資料庫約束擋下 → 轉成 409，不是 500。"""
    import app.routers.appointments as ap

    s, e = _slot()
    assert _create(client, auth, w["staff"], w["case"], w["room"], s, e).status_code == 201
    monkeypatch.setattr(ap, "assert_room_free", lambda *a, **k: None)
    r = _create(client, auth, w["staff"], w["case2"], w["room"], s, e)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "2B" in detail
    start_local = s.astimezone(TZ8)
    assert f"{start_local:%H:%M}" in detail
    for banned in ("王小明", "李小華", "林心理師", "陳心理師", "憂鬱"):
        assert banned not in r.text


# ---- 應用層：訊息與規則 -------------------------------------------------------
def test_conflict_message_names_room_and_period_only(client, auth, w):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    r = _create(client, auth, w["staff"], w["case2"], w["room"], s + timedelta(minutes=30), e + timedelta(minutes=30))
    assert r.status_code == 409
    d = r.json()["detail"]
    sl = s.astimezone(TZ8)
    el = e.astimezone(TZ8)
    assert d == f"診間 2B 在 {sl:%m/%d %H:%M}–{el:%H:%M} 已被使用"
    for banned in ("王小明", "林心理師"):
        assert banned not in r.text


def test_absent_releases_room_for_rebooking(client, auth, w):
    s, e = _slot(days=0, hour=9)
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s, e).status_code == 409
    r = client.put(f"/appointments/{a['id']}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice"})
    assert r.status_code == 200
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s, e).status_code == 201


def test_cancel_releases_room(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s, e).status_code == 201


def test_arrived_still_occupies(client, auth, w):
    s, e = _slot(days=0, hour=9)
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"])).status_code == 200
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s, e).status_code == 409


def test_batch_conflict_rolls_back_whole_batch(client, auth, w):
    s, e = _slot()
    # 第 3 週那天已被占
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s + timedelta(days=14), e + timedelta(days=14)).status_code == 201
    slots = [{"start_time": (s + timedelta(days=7 * i)).isoformat(), "end_time": (e + timedelta(days=7 * i)).isoformat()}
             for i in range(4)]
    r = client.post("/appointments/batch", headers=auth(w["staff"]),
                    json={"case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000, "slots": slots})
    assert r.status_code == 409
    assert "2B" in r.json()["detail"] and "王小明" not in r.text
    listed = client.get("/appointments", headers=auth(w["admin"])).json()
    assert len(listed) == 1  # 整批沒有建立，只剩原本那筆


# ---- 預約與活動雙向 -----------------------------------------------------------
def _event(db, room, start, end, setup_start=None, user=None):
    ev = Event(name="秘密講座名稱", room_id=room.id, start_at=start, end_at=end,
               setup_start_at=setup_start, setup_end_at=start if setup_start else None,
               borrower_type="external", borrower_name="外部講師")
    db.add(ev)
    db.commit()
    return ev


def test_appointment_cannot_overlap_event_including_setup(client, auth, w, db):
    s, e = _slot(hour=15)
    _event(db, w["room"], s, e, setup_start=s - timedelta(minutes=45))
    r = _create(client, auth, w["staff"], w["case"], w["room"], s - timedelta(minutes=30), s)
    assert r.status_code == 409  # 場佈時間也佔用
    assert "活動" in r.json()["detail"] and "2B" in r.json()["detail"]
    assert "秘密講座名稱" not in r.text and "外部講師" not in r.text
    assert _create(client, auth, w["staff"], w["case"], w["room"], e, e + timedelta(hours=1)).status_code == 201


def test_event_cannot_overlap_appointment(client, auth, w):
    s, e = _slot(hour=11)
    assert _create(client, auth, w["staff"], w["case"], w["room"], s, e).status_code == 201
    r = client.post("/events", headers=auth(w["staff"]), json={
        "name": "講座", "room_id": w["room"].id, "start_at": s.isoformat(), "end_at": e.isoformat(),
        "borrower_type": "external", "borrower_name": "外部講師"})
    assert r.status_code == 409


def test_released_appointment_does_not_block_event(client, auth, w):
    s, e = _slot(hour=11)
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    r = client.post("/events", headers=auth(w["staff"]), json={
        "name": "講座", "room_id": w["room"].id, "start_at": s.isoformat(), "end_at": e.isoformat(),
        "borrower_type": "external", "borrower_name": "外部講師"})
    assert r.status_code == 201


# ---- 行政改期、改房 -----------------------------------------------------------
def test_staff_can_move_room_only_to_free_room(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"room_id": w["room2"].id})
    assert r.status_code == 200 and r.json()["room_id"] == w["room2"].id


def test_room_only_change_into_occupied_room_is_409(client, auth, w):
    """只改房、不改時間也必須檢查（修正：以前只有改時間才檢查）。"""
    s, e = _slot()
    _create(client, auth, w["staff"], w["case2"], w["room2"], s, e)
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"room_id": w["room2"].id})
    assert r.status_code == 409
    assert "3C" in r.json()["detail"] and "李小華" not in r.text
    still = client.get(f"/appointments/{a['id']}", headers=auth(w["admin"])).json()
    assert still["room_id"] == w["room"].id


def test_reschedule_onto_occupied_slot_is_409_and_self_overlap_ok(client, auth, w):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case2"], w["room"], s + timedelta(hours=3), e + timedelta(hours=3))
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    bad = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                     json={"start_time": (s + timedelta(hours=3)).isoformat(), "end_time": (e + timedelta(hours=3)).isoformat()})
    assert bad.status_code == 409
    # 往後延 30 分鐘，與自己原本的時段重疊：不算衝突
    ok = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]),
                    json={"start_time": (s + timedelta(minutes=30)).isoformat(), "end_time": (e + timedelta(minutes=30)).isoformat()})
    assert ok.status_code == 200


def test_therapist_can_change_room_of_own_appointment(client, auth, w):
    """隔離單位是心理師：自己的預約可改診間（仍會檢查診間衝突）。"""
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["t"]), json={"room_id": w["room2"].id})
    assert r.status_code == 200 and r.json()["room_id"] == w["room2"].id


# ---- 空房查詢 -----------------------------------------------------------------
def _avail(client, auth, who, s, e, **q):
    params = {"start": s.isoformat(), "end": e.isoformat(), **q}
    return client.get("/rooms/availability", params=params, headers=auth(who))


def test_availability_excludes_occupied_and_event_rooms(client, auth, w, db):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    _event(db, w["room2"], s, e)
    r = _avail(client, auth, w["staff"], s, e)
    assert r.status_code == 200
    assert {x["room_code"] for x in r.json()} == {"2C"}


def test_availability_includes_released_rooms(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    assert {x["room_code"] for x in _avail(client, auth, w["staff"], s, e).json()} == {"2B", "2C", "3C"}


def test_availability_prefer_type_first_and_exclude_self(client, auth, w):
    s, e = _slot()
    codes = [x["room_code"] for x in _avail(client, auth, w["staff"], s, e, prefer="play").json()]
    assert codes[0] == "2C"
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert "2B" not in {x["room_code"] for x in _avail(client, auth, w["staff"], s, e).json()}
    mine = {x["room_code"] for x in _avail(client, auth, w["staff"], s, e, exclude_appointment_id=a["id"]).json()}
    assert "2B" in mine


def test_availability_bad_range_and_bad_prefer(client, auth, w):
    s, e = _slot()
    assert _avail(client, auth, w["staff"], e, s).status_code == 400
    assert _avail(client, auth, w["staff"], s, e, prefer="x").status_code == 422


def test_availability_needs_login_and_leaks_nothing(client, auth, w):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    assert client.get("/rooms/availability", params={"start": s.isoformat(), "end": e.isoformat()}).status_code in (401, 403)
    r = _avail(client, auth, w["t2"], s, e)  # 心理師也能查，但只拿到空房本身
    assert r.status_code == 200
    for banned in ("王小明", "林心理師", "R-TEST", "appointment"):
        assert banned not in r.text
    assert all(set(x) <= {"id", "name", "floor", "room_code", "room_type", "has_special_equipment", "notes", "is_active", "sort_order"} for x in r.json())


# ---- 心理師只看到「已佔用」，不顯示姓名 ---------------------------------------
def test_occupied_view_shows_no_therapist_name(client, auth, w):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    r = client.get(f"/appointments?room_id={w['room'].id}", headers=auth(w["t2"]))
    assert r.json() == []  # 他人的場次一律不在 /appointments；佔用走 /rooms/occupancy
    r = client.get("/rooms/occupancy", params={"start": (s - timedelta(days=1)).isoformat(),
                                               "end": (e + timedelta(days=1)).isoformat()}, headers=auth(w["t2"]))
    assert len(r.json()) == 1
    assert "林心理師" not in r.text and "王小明" not in r.text


# ---- list_overlaps.py（唯讀）與 migration 掃描 --------------------------------
@pytest.fixture()
def no_constraint(db, w):
    """暫時拿掉約束，才能造出歷史重疊資料；結束後清掉測試資料並復原約束。"""
    db.execute(text(f"ALTER TABLE appointments DROP CONSTRAINT {CONSTRAINT}"))
    db.commit()
    yield
    db.rollback()
    db.execute(text("DELETE FROM appointments"))
    db.commit()
    if not _has_constraint(db):
        _migration().upgrade_with(db)


def _load_migration_module():
    path = API_DIR / "alembic" / "versions" / "zh8d2e3f4a5d_room_exclusion.py"
    spec = importlib.util.spec_from_file_location("zh8d2e3f4a5d_room_exclusion", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Mig:
    def __init__(self):
        self.mod = _load_migration_module()

    def _run(self, fn_name):
        # 注意：呼叫前測試的 db session 必須先 rollback，否則它握著讀鎖，ALTER TABLE 會永遠等下去
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                getattr(self.mod, fn_name)()

    def upgrade(self):
        self._run("upgrade")

    def downgrade(self):
        self._run("downgrade")

    def upgrade_with(self, db):
        db.rollback()
        self.upgrade()


def _migration():
    return _Mig()


def _make_overlaps(db, w):
    s, e = _slot(hour=9)
    _sql_insert(db, "OV-1", w["t"].id, w["room"].id, s, e)
    _sql_insert(db, "OV-2", w["t2"].id, w["room"].id, s + timedelta(minutes=30), e + timedelta(minutes=30))  # 診間重疊
    _sql_insert(db, "OV-3", w["t"].id, w["room2"].id, s + timedelta(minutes=15), e)                           # 與 OV-1 心理師重疊
    _sql_insert(db, "OV-4", w["t2"].id, w["room"].id, s, e, status="cancelled")                                # 不算
    db.commit()


def _run_script(*args):
    env = dict(os.environ)
    return subprocess.run([sys.executable, "-I", str(API_DIR / "scripts" / "list_overlaps.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(API_DIR))


@pytest.mark.real_commit
def test_list_overlaps_reports_room_and_therapist_overlaps(db, w, no_constraint):
    _make_overlaps(db, w)
    before = db.execute(text("SELECT count(*) FROM appointments")).scalar()
    p = _run_script()
    assert p.returncode == 1, p.stderr
    out = p.stdout
    assert "診間重疊：1 組" in out and "OV-1" in out and "OV-2" in out
    assert "心理師重疊：" in out and "OV-3" in out
    assert "OV-4" not in out                       # cancelled 不算重疊
    for banned in ("王小明", "李小華", "林心理師", "陳心理師"):
        assert banned not in out                   # 不含個資
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM appointments")).scalar() == before  # 唯讀


@pytest.mark.real_commit
def test_list_overlaps_clean_db_exits_zero(db, w, make_appt):
    s, e = _slot()
    _sql_insert(db, "OK-1", w["t"].id, w["room"].id, s, e)
    db.commit()
    p = _run_script()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "沒有重疊" in p.stdout


@pytest.mark.real_commit
def test_list_overlaps_requires_database_url():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    p = subprocess.run([sys.executable, "-I", str(API_DIR / "scripts" / "list_overlaps.py")],
                       capture_output=True, text=True, env=env, cwd=str(API_DIR))
    assert p.returncode == 2


def test_list_overlaps_script_is_read_only_by_construction():
    src = (API_DIR / "scripts" / "list_overlaps.py").read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in src
    for word in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE"):
        assert word not in src.upper().replace("UPDATE_", "")


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_refuses_when_overlaps_exist_and_lists_them(db, w, no_constraint):
    _make_overlaps(db, w)
    db.rollback()
    with pytest.raises(RuntimeError) as exc:
        _migration().upgrade()
    msg = str(exc.value)
    assert "2B" in msg and "OV-1" in msg and "OV-2" in msg
    assert "list_overlaps.py" in msg
    assert "王小明" not in msg
    assert not _has_constraint(db)  # 沒有建出一半的約束


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_upgrade_and_downgrade_roundtrip(db, w, no_constraint):
    s, e = _slot()
    _sql_insert(db, "M-1", w["t"].id, w["room"].id, s, e)
    _sql_insert(db, "M-2", w["t2"].id, w["room"].id, s, e, status="no_show")   # 釋出的不算重疊
    db.commit()
    mig = _migration()
    db.rollback()                       # 放掉讀鎖，遷移才拿得到獨佔鎖
    mig.upgrade()
    assert _has_constraint(db)
    with pytest.raises(IntegrityError):
        _sql_insert(db, "M-3", w["t2"].id, w["room"].id, s, e)
    db.rollback()
    mig.downgrade()
    assert not _has_constraint(db)
    # 資料沒被動到
    assert db.execute(text("SELECT count(*) FROM appointments")).scalar() == 2
    db.rollback()
    mig.upgrade()
    assert _has_constraint(db)


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_chain_is_linear_after_zg7():
    import re

    txt = (API_DIR / "alembic" / "versions" / "zh8d2e3f4a5d_room_exclusion.py").read_text(encoding="utf-8")
    assert re.search(r'^down_revision = "zg7c1d2e3f4c"', txt, re.M)
    children = [p.name for p in (API_DIR / "alembic" / "versions").glob("*.py")
                if 'down_revision = "zh8d2e3f4a5d"' in p.read_text(encoding="utf-8")]
    assert children == ["zi9e3f4a5b6e_rooms_active_sort.py"]  # 線性：之後只有 F 的 migration 接在後面
    assert "DROP TABLE" not in txt.upper() and "drop_table" not in txt  # 只新增，不刪表
