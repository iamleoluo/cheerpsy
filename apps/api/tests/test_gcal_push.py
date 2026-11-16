"""Google 日曆同步 PR C：outbox、工作者、事件推送。

全部不連外網：Calendar 用戶端換成 fake（沿用 PR B 的 FakeCalendar 並加上事件）。重點：
- 預約寫入（新增／批次／改期／換診間／取消／未到／報到／刪除／結案）在同一交易入列，且 Google 失敗不影響預約 API。
- 事件 id 由預約 id 決定；改期是更新同一事件；payload_hash 沒變不打網路。
- 429 指數退避、用盡次數標 failed；授權失效 → blocked；沒有日曆 → blocked，建立後自動解封。
- 事件內容永遠沒有完整姓名、電話、Email、主訴、金額。
"""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from psycopg2.extras import DateTimeTZRange
from sqlalchemy import text

from app.auth.password import hash_password
from app.database import SessionLocal, engine
from app.models.appointment import Appointment
from app.models.gcal import AppointmentGoogleEvent, ClinicSettings, GcalOutbox, GoogleCalendar, GoogleOAuthConnection
from app.models.room import Room
from app.services import gcal_client, gcal_push, gcal_sync, gcal_titles, google_oauth
from app.services.gcal_client import CalendarApiError, GcalNotConnected
from test_gcal_share import OWNER, FakeCalendar  # noqa: E402  (tests/ 在 sys.path 上)

API_DIR = Path(__file__).resolve().parents[1]
CAL = "cal-t1@group.calendar.google.com"
CAL2 = "cal-t2@group.calendar.google.com"


# ---------------------------------------------------------------------------
# Fake：FakeCalendar 加上事件（含「曾刪除的同 id 事件 insert 回 409、update 可復活」）
# ---------------------------------------------------------------------------
class FakeEvents(FakeCalendar):
    def __init__(self):
        super().__init__()
        self.events: dict[tuple[str, str], dict] = {}
        self.tombstones: set[tuple[str, str]] = set()
        self.fail_event: CalendarApiError | None = None
        self.missing_calendars: set[str] = set()

    def _ev_guard(self, cal):
        if self.fail_event:
            raise self.fail_event
        if cal in self.missing_calendars:
            raise CalendarApiError(404, "notFound")

    def insert_event(self, calendar_id, body):
        self.calls.append(("insert_event", calendar_id, body["id"]))
        self._ev_guard(calendar_id)
        key = (calendar_id, body["id"])
        if key in self.events or key in self.tombstones:
            raise CalendarApiError(409, "duplicate")
        self.events[key] = body

    def update_event(self, calendar_id, event_id, body):
        self.calls.append(("update_event", calendar_id, event_id))
        self._ev_guard(calendar_id)
        key = (calendar_id, event_id)
        if key not in self.events and key not in self.tombstones:
            raise CalendarApiError(404, "notFound")
        self.tombstones.discard(key)
        self.events[key] = body

    def delete_event(self, calendar_id, event_id):
        self.calls.append(("delete_event", calendar_id, event_id))
        self._ev_guard(calendar_id)
        key = (calendar_id, event_id)
        if key not in self.events:
            raise CalendarApiError(404 if key not in self.tombstones else 410, "notFound")
        del self.events[key]
        self.tombstones.add(key)

    def event_calls(self):
        return [c for c in self.calls if c[0].endswith("_event")]


_REAL_GET_CLIENT = gcal_client.get_calendar_client  # 在任何 monkeypatch 之前留下真的
NOW = datetime.now(timezone.utc)


def now_():
    return datetime.now(timezone.utc) + timedelta(seconds=1)


def _slot(day=2, hour=10):
    s = (NOW + timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(hours=1)


@pytest.fixture()
def fake(monkeypatch, db):
    f = FakeEvents()
    db.add(GoogleOAuthConnection(id=1, google_email=OWNER, status="active", refresh_token_enc="x",
                                 scopes=" ".join(google_oauth.CALENDAR_SCOPES)))
    db.commit()
    monkeypatch.setattr(gcal_client, "get_calendar_client", lambda _db: f)
    return f


@pytest.fixture()
def w(make_user, make_case, room, db, fake):
    t = make_user("therapist", name="林心理師")
    t2 = make_user("therapist", name="陳心理師")
    staff = make_user("staff")
    admin = make_user("admin")
    admin.password_hash = hash_password("pw123456")
    db.commit()
    case = make_case(t, "王小明", case_code="C-1042", phone="0912-345-678")
    room2 = Room(name="晤談室 3C", floor=3, room_code="3C")
    db.add_all([room2,
                GoogleCalendar(therapist_id=t.id, google_calendar_id=CAL, summary="林心理師 · Cheerpsy", share_status="invited"),
                GoogleCalendar(therapist_id=t2.id, google_calendar_id=CAL2, summary="陳心理師 · Cheerpsy", share_status="invited")])
    db.commit()
    return dict(t=t, t2=t2, staff=staff, admin=admin, case=case, room=room, room2=room2)


def run(fake, now=None, client_factory=None):
    # 預設往後一秒：資料庫的 now() 與這裡的時鐘有毫秒級誤差，別讓「剛入列」的工作剛好落在邊界外
    return gcal_push.run_once(SessionLocal, client_factory or (lambda _db: fake), now=now or now_())


def create(client, auth, w, day=2, hour=10, **extra):
    s, e = _slot(day, hour)
    body = {"case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person",
            "start_time": s.isoformat(), "end_time": e.isoformat(), **extra}
    r = client.post("/appointments", json=body, headers=auth(w["staff"]))
    assert r.status_code == 201, r.text
    return r.json()


def outbox(db, appt_id=None):
    db.expire_all()
    q = db.query(GcalOutbox)
    if appt_id is not None:
        q = q.filter(GcalOutbox.appointment_id == appt_id)
    return q.order_by(GcalOutbox.id).all()


def job(db, appt_id):
    rows = outbox(db, appt_id)
    assert len(rows) == 1, rows
    return rows[0]


def ev(fake, appt_id, cal=CAL):
    return fake.events.get((cal, gcal_titles.event_id(appt_id)))


# ---------------------------------------------------------------------------
# 標題與隱私（純函式）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("陳小美", "陳小"), ("歐陽小明", "歐陽小"), ("王明", "王"), ("司馬光明", "司馬光"),
    ("歐陽明", "歐陽"),  # 複姓三字名：取三字會等於全名，只顯示複姓
    ("王", None), ("", None), (None, None), ("王小明明", None),  # 單字、空、四字非複姓：無法安全縮寫
    ("Mei Chen", "Mei C."), ("john  smith", "john S."), ("Madonna", None), ("王Mei", None),
])
def test_abbreviate_name(name, expected):
    assert gcal_titles.abbreviate_name(name) == expected


def test_abbreviation_never_equals_full_name():
    rng = random.Random(7)
    pool = "王李張劉陳楊黃趙吳周歐陽司馬小明美華玲"
    for _ in range(500):
        n = "".join(rng.choice(pool) for _ in range(rng.randint(1, 6)))
        out = gcal_titles.abbreviate_name(n)
        assert out is None or (out != n and len(out) < len(n))
    for n in ("Mei Chen", "A B", "Anna Maria Lopez"):
        assert gcal_titles.abbreviate_name(n) not in (None, n)


def _appt(db, w, **kw):
    s, e = _slot()
    a = Appointment(appointment_number="X-1", case_id=w["case"].id, therapist_id=w["t"].id, room_id=w["room"].id,
                    session_type="in_person", time_range=DateTimeTZRange(s, e), amount=1500, **kw)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_title_formats(db, w):
    a = _appt(db, w)
    a.amount = 0  # 沒有金額：標題不加那一段
    assert gcal_titles.event_title(a, "type_room") == "諮商 · 2B"
    assert gcal_titles.event_title(a, "type_room_code") == "諮商 · 2B · C-1042"
    assert gcal_titles.event_title(a, "type_room_abbrev") == "諮商 · 2B · 王小"
    assert gcal_titles.event_title(a, "type_room_name") == "諮商 · 2B · 王小明"
    a.amount = 1500  # 有金額：任一格式結尾都加
    assert gcal_titles.event_title(a, "type_room_name") == "諮商 · 2B · 王小明 · $1,500"
    assert gcal_titles.event_title(a, "type_room") == "諮商 · 2B · $1,500"
    a.amount = 1500.5
    assert gcal_titles.event_title(a, "type_room") == "諮商 · 2B · $1,500.50"
    a.amount = 1500
    a.is_intake = True
    assert gcal_titles.event_title(a, "type_room") == "初診 · 2B · $1,500"
    a.is_intake = False
    a.session_type = "online"
    assert gcal_titles.event_title(a, "type_room_abbrev") == "諮商 · 線上 · 王小 · $1,500"
    a.session_type = "outdoor"
    assert gcal_titles.event_title(a, "type_room") == "外展 · $1,500"
    a.session_type, a.room = "in_person", None
    a.amount = None
    assert gcal_titles.event_title(a, "type_room") == "諮商"  # 缺診間、沒金額：不留空的分隔


def test_format_amount():
    f = gcal_titles.format_amount
    assert f(1500) == "$1,500" and f("2000.00") == "$2,000" and f(1234.5) == "$1,234.50" and f(1000000) == "$1,000,000"
    assert f(0) is None and f(None) is None and f(-5) is None and f("abc") is None


def test_description_sections_and_amount_line(db, w):
    a = _appt(db, w)
    assert gcal_titles.event_description(a) == gcal_titles.DESCRIPTION + "\n金額：$1,500"
    a.amount = None
    assert gcal_titles.event_description(a) == gcal_titles.DESCRIPTION  # 沒金額：不顯示那一行
    a.amount = 1500
    d = gcal_titles.event_description(a, [("預約備註", "帶孩子來"), ("備註給心理師", "  注意事項  "), ("空的", "  ")])
    assert "【預約備註】\n帶孩子來" in d and "【備註給心理師】\n注意事項" in d and "空的" not in d
    assert d.index("預約備註") < d.index("備註給心理師")  # 分段標示、順序固定


def test_title_degrades_instead_of_leaking_name(db, w):
    a = _appt(db, w)
    w["case"].case_code = None
    a.amount = 0
    assert gcal_titles.event_title(a, "type_room_code") == "諮商 · 2B"  # 沒有代號 → (a)，不改塞姓名
    w["case"].name = "王"
    assert gcal_titles.event_title(a, "type_room_abbrev") == "諮商 · 2B"  # 無法縮寫 → (a)
    assert gcal_titles.event_title(a, "type_room_name") == "諮商 · 2B · 王"  # (d) 就是全名


def test_only_format_d_ever_outputs_the_full_name(db, w):
    a = _appt(db, w)
    for fmt in ("type_room", "type_room_code", "type_room_abbrev"):
        assert "王小明" not in gcal_titles.event_title(a, fmt) and "王小明" not in gcal_titles.event_description(a)
    assert "王小明" in gcal_titles.event_title(a, "type_room_name")


def test_event_body_has_no_sensitive_data(db, w):
    a = _appt(db, w)
    w["case"].chief_complaint = "憂鬱與失眠"
    for fmt in ("type_room", "type_room_code", "type_room_abbrev", "type_room_name"):
        body = gcal_titles.event_body(a, fmt)
        blob = json.dumps(body, ensure_ascii=False)
        # 電話、主訴、Email、內部編號、心理師姓名一律不放（金額與 (d) 的全名是診所決定要放的）
        for secret in ("0912", "憂鬱", "@", "林心理師", a.appointment_number):
            assert secret not in blob, (fmt, secret)
        assert "金額：$1,500" in body["description"] and body["summary"].endswith("$1,500")
    assert gcal_titles.event_body(a, "type_room")["description"].startswith(gcal_titles.DESCRIPTION)
    assert body["start"]["timeZone"] == "Asia/Taipei" and body["start"]["dateTime"].endswith("+08:00")
    assert body["id"] == gcal_titles.event_id(a.id)


def test_event_id_is_valid_and_deterministic():
    import re
    assert gcal_titles.event_id(5) == gcal_titles.event_id(5) != gcal_titles.event_id(6)
    assert re.fullmatch(r"[a-v0-9]{5,1024}", gcal_titles.event_id(123456))


# ---------------------------------------------------------------------------
# 入列（同交易）
# ---------------------------------------------------------------------------
def test_create_enqueues_one_upsert_and_worker_pushes_event(client, auth, w, fake, db):
    a = create(client, auth, w)
    j = job(db, a["id"])
    assert (j.job_type, j.status, j.attempts, j.dedupe_key) == ("upsert_event", "pending", 0, f"appt:{a['id']}")
    assert run(fake) == 1
    body = ev(fake, a["id"])
    assert body["summary"] == "諮商 · 2B · 王小明" and body["extendedProperties"]["private"]["cheerpsyAppointmentId"] == str(a["id"])
    assert job(db, a["id"]).status == "done"
    m = db.get(AppointmentGoogleEvent, a["id"])
    assert m.google_calendar_id == CAL and m.google_event_id == gcal_titles.event_id(a["id"]) and m.last_status == "pushed"
    assert run(fake) == 0  # 沒事了


def test_batch_create_enqueues_each(client, auth, w, fake, db):
    s1, e1 = _slot(3)
    s2, e2 = _slot(4)
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person",
        "slots": [{"start_time": s1.isoformat(), "end_time": e1.isoformat()},
                  {"start_time": s2.isoformat(), "end_time": e2.isoformat()}]})
    assert r.status_code == 201, r.text
    assert len(outbox(db)) == 2
    run(fake)
    assert len(fake.events) == 2


def test_reschedule_updates_same_event_not_recreate(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    s, e = _slot(5, 14)
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 200, r.text
    fake.clear_calls()
    run(fake)
    assert [c[0] for c in fake.event_calls()] == ["update_event"]  # 不是先刪再建
    assert len(fake.events) == 1 and ev(fake, a["id"])["start"]["dateTime"].startswith(s.astimezone(gcal_titles.TAIPEI).strftime("%Y-%m-%dT%H"))


def test_room_change_updates_title(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"room_id": w["room2"].id})
    run(fake)
    assert ev(fake, a["id"])["summary"] == "諮商 · 3C · 王小明"


def test_two_reschedules_before_worker_runs_keep_one_job(client, auth, w, fake, db):
    a = create(client, auth, w)
    for day in (6, 7):
        s, e = _slot(day)
        client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    j = job(db, a["id"])  # 仍只有一列
    assert j.version == 3 and j.status == "pending"
    run(fake)
    assert len(fake.events) == 1 and len(fake.ops("insert_event")) == 1
    assert ev(fake, a["id"])["start"]["dateTime"][:10] == _slot(7)[0].astimezone(gcal_titles.TAIPEI).strftime("%Y-%m-%d")


@pytest.mark.parametrize("how", ["cancel", "absent"])
def test_cancel_and_no_show_delete_event(client, auth, w, fake, db, how):
    a = create(client, auth, w)
    run(fake)
    assert ev(fake, a["id"]) is not None
    if how == "cancel":
        assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    else:
        assert client.put(f"/appointments/{a['id']}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice"}).status_code == 200
    assert job(db, a["id"]).job_type == "delete_event"
    run(fake)
    assert ev(fake, a["id"]) is None
    assert db.get(AppointmentGoogleEvent, a["id"]).last_status == "deleted"


def test_delete_when_event_already_gone_counts_as_success(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    fake.events.clear()  # 有人在 Google 上手動刪了
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    run(fake)
    assert job(db, a["id"]).status == "done"


def test_arrive_keeps_event_without_calling_google_when_content_same(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    fake.clear_calls()
    assert client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"]), json={}).status_code == 200
    assert job(db, a["id"]).job_type == "upsert_event"  # 狀態變更有入列
    run(fake)
    assert fake.event_calls() == []  # 內容沒變 → hash 相同 → 不打 API
    assert ev(fake, a["id"]) is not None and job(db, a["id"]).status == "done"


def test_hard_delete_removes_google_event(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    r = client.request("DELETE", "/appointments", headers=auth(w["staff"]), json={"ids": [a["id"]]})
    assert r.status_code == 200, r.text
    assert job(db, a["id"]).job_type == "delete_event"
    run(fake)
    assert ev(fake, a["id"]) is None and job(db, a["id"]).status == "done"


def test_hard_delete_of_never_pushed_appointment_enqueues_nothing_new(client, auth, w, fake, db):
    a = create(client, auth, w)  # 還沒推送過
    r = client.request("DELETE", "/appointments", headers=auth(w["staff"]), json={"ids": [a["id"]]})
    assert r.status_code == 200
    run(fake)
    assert fake.event_calls() == [] and job(db, a["id"]).status == "done"  # 預約已不存在：no-op


def test_case_close_cancels_future_appointments_and_enqueues_deletes(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    r = client.post(f"/cases/{w['case'].id}/close", headers=auth(w["admin"]), json={"password": "pw123456", "reason": "測試"})
    assert r.status_code == 200, r.text
    assert job(db, a["id"]).job_type == "delete_event"
    run(fake)
    assert ev(fake, a["id"]) is None


def test_non_event_changes_do_not_enqueue(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    row = db.get(Appointment, a["id"])
    row.video_link = "https://meet.example/x"
    db.commit()
    assert job(db, a["id"]).version == 1 and job(db, a["id"]).status == "done"


def test_rolled_back_appointment_leaves_no_job(client, auth, w, fake, db):
    s, e = _slot()
    db.add(Appointment(appointment_number="RB-1", case_id=w["case"].id, therapist_id=w["t"].id, room_id=w["room"].id,
                       session_type="in_person", time_range=DateTimeTZRange(s, e), amount=1))
    db.flush()
    assert len(outbox(db)) == 1
    db.rollback()
    assert outbox(db) == []


# ---------------------------------------------------------------------------
# 未連結／授權失效：預約流程不受影響
# ---------------------------------------------------------------------------
def test_not_connected_appointment_api_still_works_and_nothing_queued(client, auth, w, db):
    db.query(GoogleOAuthConnection).delete()
    db.commit()
    a = create(client, auth, w)
    assert outbox(db, a["id"]) == []  # 沒有連線不入列（上線時用「全部重新同步」補）


def test_token_invalid_enqueues_blocked_and_retry_after_reconnect(client, auth, w, fake, db):
    db.get(GoogleOAuthConnection, 1).status = "token_invalid"
    db.commit()
    a = create(client, auth, w)
    assert job(db, a["id"]).status == "blocked"
    assert run(fake) == 0
    db.get(GoogleOAuthConnection, 1).status = "active"
    db.commit()
    r = client.post("/settings/google/sync/retry", headers=auth(w["staff"]))
    assert r.status_code == 200 and "1" in r.json()["message"]
    assert job(db, a["id"]).status == "pending"
    run(fake)
    assert ev(fake, a["id"]) is not None


def test_google_failure_never_fails_the_appointment_api(client, auth, w, fake, db):
    fake.fail_event = CalendarApiError(500, "backendError")  # 工作者跑不動，API 也根本不會呼叫 Google
    a = create(client, auth, w)
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"])).status_code == 200


def test_invalid_grant_blocks_all_jobs(client, auth, w, fake, db):
    a = create(client, auth, w)
    b = create(client, auth, w, day=3)

    def factory(_db):
        raise GcalNotConnected("Google 授權已失效，請管理員重新連結", token_invalid=True)

    assert run(fake, client_factory=factory) == 0
    assert {job(db, x["id"]).status for x in (a, b)} == {"blocked"}
    assert "重新連結" in job(db, a["id"]).last_error


def test_transient_token_problem_keeps_jobs_pending(client, auth, w, fake, db):
    a = create(client, auth, w)

    def factory(_db):
        raise GcalNotConnected("暫時無法向 Google 取得授權，請稍後再試", transient=True)

    run(fake, client_factory=factory)
    assert job(db, a["id"]).status == "pending" and job(db, a["id"]).attempts == 0


def test_real_client_invalid_grant_marks_connection_and_blocks(client, auth, w, db, monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import settings
    from app.services import secret_box

    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/cb")
    conn = db.get(GoogleOAuthConnection, 1)
    conn.refresh_token_enc = secret_box.encrypt("R")
    db.commit()
    a = create(client, auth, w)

    def refresh(self, token):
        raise google_oauth.GoogleOAuthError("invalid_grant")

    monkeypatch.setattr(google_oauth.GoogleOAuthClient, "refresh_access_token", refresh)
    gcal_push.run_once(SessionLocal, _REAL_GET_CLIENT)
    db.expire_all()
    assert db.get(GoogleOAuthConnection, 1).status == "token_invalid"
    assert job(db, a["id"]).status == "blocked"


# ---------------------------------------------------------------------------
# 日曆條件
# ---------------------------------------------------------------------------
def test_no_calendar_blocks_then_provision_unblocks_and_pushes(client, auth, w, fake, db, make_user):
    t3 = make_user("therapist", name="黃心理師", gcal_share_email="huang@gmail.com")
    from app.models.case import Case
    c3 = Case(name="趙小花", therapist_id=t3.id, status="ongoing")
    db.add(c3)
    db.commit()
    s, e = _slot(3)
    r = client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": c3.id, "room_id": w["room"].id, "session_type": "in_person",
        "start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    run(fake)
    j = job(db, aid)
    assert j.status == "blocked" and "還沒有 Google 日曆" in j.last_error
    assert client.post(f"/settings/google/therapists/{t3.id}/provision", headers=auth(w["staff"])).status_code == 200
    assert job(db, aid).status == "pending"  # 建好日曆自動解封並排入
    run(fake)
    cal = db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == t3.id).one()
    assert fake.events[(cal.google_calendar_id, gcal_titles.event_id(aid))]["summary"].startswith("諮商 · 2B")


def test_calendar_missing_on_google_blocks_and_marks_row(client, auth, w, fake, db):
    a = create(client, auth, w)
    fake.missing_calendars.add(CAL)
    run(fake)
    assert job(db, a["id"]).status == "blocked"
    assert db.query(GoogleCalendar).filter(GoogleCalendar.google_calendar_id == CAL).one().is_missing is True


def test_frozen_calendar_receives_no_updates(client, auth, w, fake, db):
    db.query(GoogleCalendar).filter(GoogleCalendar.google_calendar_id == CAL).one().is_active = False
    db.commit()
    a = create(client, auth, w)
    run(fake)
    assert fake.event_calls() == [] and job(db, a["id"]).status == "done"


def test_frozen_calendar_keeps_own_events_but_cleans_reassigned_ones(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    cal = db.query(GoogleCalendar).filter(GoogleCalendar.google_calendar_id == CAL).one()
    cal.is_active = False
    db.commit()
    # 他自己的場次被取消：凍結 → 不動日曆
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    fake.clear_calls()
    run(fake)
    assert fake.event_calls() == [] and ev(fake, a["id"]) is not None
    # 另一個場次改派給別人：隱私清理仍要把它從他的日曆移除
    b = create(client, auth, w, day=3)
    cal.is_active = True
    db.commit()
    run(fake)
    cal.is_active = False
    db.commit()
    row = db.get(Appointment, b["id"])
    row.therapist_id = w["t2"].id
    db.commit()
    run(fake)
    assert ev(fake, b["id"], CAL) is None and ev(fake, b["id"], CAL2) is not None


def test_reassign_therapist_moves_event_between_calendars(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    row = db.get(Appointment, a["id"])
    row.therapist_id = w["t2"].id
    db.commit()
    run(fake)
    assert ev(fake, a["id"], CAL) is None and ev(fake, a["id"], CAL2) is not None
    assert db.get(AppointmentGoogleEvent, a["id"]).google_calendar_id == CAL2


def test_each_calendar_only_contains_its_own_therapists_sessions(client, auth, w, fake, db, make_case):
    c2 = make_case(w["t2"], "李小華")
    create(client, auth, w)
    s, e = _slot(3)
    client.post("/appointments", headers=auth(w["staff"]), json={
        "case_id": c2.id, "room_id": w["room2"].id, "session_type": "in_person", "start_time": s.isoformat(), "end_time": e.isoformat()})
    run(fake)
    cals = {}
    for (cal, _id), body in fake.events.items():
        cals.setdefault(cal, []).append(body["summary"])
    assert sorted(cals) == [CAL, CAL2] and all(len(v) == 1 for v in cals.values())
    assert "李" not in json.dumps(cals[CAL], ensure_ascii=False) and "王" not in json.dumps(cals[CAL2], ensure_ascii=False)


def test_title_format_setting_is_used(client, auth, w, fake, db):
    db.add(ClinicSettings(id=1, event_title_format="type_room_code"))
    db.commit()
    a = create(client, auth, w)
    db.get(Appointment, a["id"]).amount = 1500  # API 建立的預約金額為 0；金額會在標題結尾
    db.commit()
    run(fake)
    assert ev(fake, a["id"])["summary"] == "諮商 · 2B · C-1042 · $1,500"


def test_default_format_is_d_with_full_name_and_amount(client, auth, w, fake, db):
    a = create(client, auth, w)  # 沒有設定列：預設 (d)
    run(fake)
    e = ev(fake, a["id"])
    blob = json.dumps(e, ensure_ascii=False)
    assert e["summary"] == "諮商 · 2B · 王小明" and "0912" not in blob and "憂鬱" not in blob


def test_amount_change_triggers_resync_and_zero_amount_hides_line(client, auth, w, fake, db):
    a = create(client, auth, w)
    row = db.get(Appointment, a["id"])
    row.amount = 1500
    db.commit()
    run(fake)
    e = ev(fake, a["id"])
    assert e["summary"].endswith("· $1,500") and "金額：$1,500" in e["description"]
    row.amount = 2000  # 金額改了 → 入列 → 內容 hash 變 → update 同一事件
    db.commit()
    fake.clear_calls()
    run(fake)
    assert [c[0] for c in fake.event_calls()] == ["update_event"] and ev(fake, a["id"])["summary"].endswith("$2,000")
    row.amount = 0
    db.commit()
    run(fake)
    e = ev(fake, a["id"])
    assert "$" not in e["summary"] and "金額" not in e["description"]


def test_note_change_changes_hash_and_note_sections_reach_description(client, auth, w, fake, db, monkeypatch):
    a = create(client, auth, w)
    run(fake)
    assert "【" not in ev(fake, a["id"])["description"]  # 目前預約上沒有備註欄位
    monkeypatch.setattr(gcal_push, "note_sections", lambda _db, _a: [("備註給心理師", "請準備量表")])
    from app.models.gcal_hooks import enqueue_appointments
    with engine.begin() as c:  # PR D 寫備註的路徑要做的事
        enqueue_appointments(c, [a["id"]])
    fake.clear_calls()
    run(fake)
    assert [c[0] for c in fake.event_calls()] == ["update_event"]  # 備註改了 → hash 變 → 重新同步
    assert "【備註給心理師】\n請準備量表" in ev(fake, a["id"])["description"]


def test_event_deleted_on_google_is_recreated_on_next_change(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    fake.events.clear()  # 手動刪了
    s, e = _slot(8)
    client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    run(fake)
    assert ev(fake, a["id"]) is not None  # update 回 404 → 改走 insert


def test_reinsert_after_delete_resurrects_via_update(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    run(fake)
    assert (CAL, gcal_titles.event_id(a["id"])) in fake.tombstones
    db.execute(text("UPDATE appointments SET status = 'booked' WHERE id = :i"), {"i": a["id"]})  # 不經 ORM：手動入列
    db.commit()
    with engine.begin() as c:
        from app.models.gcal_hooks import enqueue_appointments
        enqueue_appointments(c, [a["id"]])
    run(fake)  # insert 回 409 → update 復活
    assert ev(fake, a["id"]) is not None


# ---------------------------------------------------------------------------
# 冪等與重試
# ---------------------------------------------------------------------------
def test_same_payload_hash_skips_network(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    with engine.begin() as c:
        from app.models.gcal_hooks import enqueue_appointments
        enqueue_appointments(c, [a["id"]])
    fake.clear_calls()
    run(fake)
    assert fake.event_calls() == [] and job(db, a["id"]).status == "done"


def test_429_backs_off_then_succeeds(client, auth, w, fake, db):
    a = create(client, auth, w)
    fake.fail_event = CalendarApiError(429, "rateLimitExceeded")
    run(fake, now=now_())
    j = job(db, a["id"])
    assert j.status == "retry" and j.attempts == 1 and "稍後自動重試" in j.last_error
    assert j.next_attempt_at > datetime.now(timezone.utc)
    assert run(fake, now=now_()) == 0  # 還沒到時間
    fake.fail_event = None
    assert run(fake, now=now_() + timedelta(minutes=30)) == 1
    assert job(db, a["id"]).status == "done" and ev(fake, a["id"]) is not None


def test_403_usage_limit_is_retried_but_plain_403_is_not_retryable(client, auth, w, fake, db):
    a = create(client, auth, w)
    fake.fail_event = CalendarApiError(403, "rateLimitExceeded")
    run(fake, now=now_())
    assert job(db, a["id"]).status == "retry"
    fake.fail_event = CalendarApiError(403, "forbidden")
    run(fake, now=now_() + timedelta(hours=1))
    assert job(db, a["id"]).status == "failed"


def test_backoff_grows_and_is_capped():
    xs = [gcal_push.backoff_seconds(n) for n in range(1, 14)]
    assert 2 <= xs[0] < 8 and all(x <= gcal_push.BACKOFF_CAP_SECONDS + 5 for x in xs)
    assert xs[5] > xs[1]


def test_gives_up_after_max_attempts_and_shows_in_status(client, auth, w, fake, db):
    a = create(client, auth, w)
    fake.fail_event = CalendarApiError(503, "backendError")
    t = now_()
    for _ in range(gcal_push.MAX_ATTEMPTS + 2):
        run(fake, now=t)
        t += timedelta(hours=1)
    j = job(db, a["id"])
    assert j.status == "failed" and j.attempts == gcal_push.MAX_ATTEMPTS and j.finished_at is not None
    r = client.get("/settings/google/sync", headers=auth(w["staff"]))
    body = r.json()
    assert body["counts"]["failed"] == 1 and body["problems"][0]["status"] == "failed"
    assert body["problems"][0]["appointment_number"] == db.get(Appointment, a["id"]).appointment_number
    fake.fail_event = None
    r = client.post("/settings/google/sync/retry", headers=auth(w["staff"]))
    assert r.status_code == 200 and r.json()["status"]["counts"]["pending"] == 1
    run(fake, now=t)
    assert job(db, a["id"]).status == "done" and ev(fake, a["id"]) is not None


def test_bad_request_fails_immediately(client, auth, w, fake, db):
    a = create(client, auth, w)
    fake.fail_event = CalendarApiError(400, "invalid")
    run(fake)
    assert job(db, a["id"]).status == "failed"


def test_unexpected_exception_does_not_kill_batch(client, auth, w, fake, db, monkeypatch):
    a = create(client, auth, w)
    b = create(client, auth, w, day=3)
    orig = gcal_push.process

    def flaky(db_, client_, appt_id):
        if appt_id == a["id"]:
            raise RuntimeError("boom")
        return orig(db_, client_, appt_id)

    monkeypatch.setattr(gcal_push, "process", flaky)
    assert run(fake) == 2
    assert job(db, a["id"]).status == "retry" and "內部錯誤" in job(db, a["id"]).last_error
    assert job(db, b["id"]).status == "done"


def test_run_once_never_raises(fake):
    def factory(_db):
        raise RuntimeError("unexpected")

    assert gcal_push.run_once(SessionLocal, factory) == 0


def test_skip_locked_two_workers_do_not_take_the_same_job(client, auth, w, fake, db):
    a = create(client, auth, w)
    with engine.connect() as c, c.begin():
        c.execute(text("SELECT id FROM gcal_outbox WHERE appointment_id = :a FOR UPDATE"), {"a": a["id"]})
        assert run(fake) == 0  # 另一個工作者正在處理這列，直接略過、不等待
    assert run(fake) == 1


def test_change_during_processing_keeps_job_pending(client, auth, w, fake, db, monkeypatch):
    a = create(client, auth, w)
    orig = gcal_push.process

    def process_and_change(db_, client_, appt_id):
        out = orig(db_, client_, appt_id)
        with engine.begin() as c:  # 處理期間預約又被改了（入列把版本加一）
            from app.models.gcal_hooks import enqueue_appointments
            enqueue_appointments(c, [appt_id])
        return out

    monkeypatch.setattr(gcal_push, "process", process_and_change)
    run(fake)
    j = job(db, a["id"])
    assert j.status == "pending" and j.version == 2  # 不會被誤標成 done
    monkeypatch.setattr(gcal_push, "process", orig)
    run(fake)
    assert job(db, a["id"]).status == "done"


def test_stale_running_job_is_reclaimed(client, auth, w, fake, db):
    a = create(client, auth, w)
    db.execute(text("UPDATE gcal_outbox SET status = 'running', claimed_at = :t WHERE appointment_id = :a"),
               {"t": NOW - timedelta(hours=1), "a": a["id"]})
    db.commit()
    assert run(fake) == 1
    assert job(db, a["id"]).status == "done"


# ---------------------------------------------------------------------------
# 全部重新同步、重試、狀態與權限
# ---------------------------------------------------------------------------
def test_resync_requires_admin_and_connection(client, auth, w, fake, db):
    assert client.post("/settings/google/sync/resync", headers=auth(w["staff"])).status_code == 403
    assert client.post("/settings/google/sync/resync", headers=auth(w["t"])).status_code == 403
    db.get(GoogleOAuthConnection, 1).status = "token_invalid"
    db.commit()
    assert client.post("/settings/google/sync/resync", headers=auth(w["admin"])).status_code == 409


def test_resync_imports_existing_appointments_within_window_and_staggers(client, auth, w, fake, db):
    db.query(GoogleOAuthConnection).update({"status": "disconnected"})
    db.commit()
    ids = [create(client, auth, w, day=d)["id"] for d in (1, 2, 3)]
    far = create(client, auth, w, day=400)["id"]  # 區間（預設往後 180 天）之外
    assert outbox(db) == []  # 沒連線時不入列
    db.query(GoogleOAuthConnection).update({"status": "active"})
    db.commit()
    r = client.post("/settings/google/sync/resync", headers=auth(w["admin"]))
    assert r.status_code == 200, r.text
    assert "3 筆新增" in r.json()["message"]
    rows = outbox(db)
    assert sorted(x.appointment_id for x in rows) == sorted(ids) and far not in {x.appointment_id for x in rows}
    times = [x.next_attempt_at for x in sorted(rows, key=lambda x: x.appointment_id)]
    assert times[2] - times[0] >= timedelta(seconds=0.5)  # 分散排程，不是同一瞬間
    run(fake, now=now_() + timedelta(minutes=5))
    assert len(fake.events) == 3
    audit = db.execute(text("SELECT operation FROM audit_log WHERE table_name = 'gcal_outbox'")).scalars().all()
    assert "RESYNC" in audit


def test_resync_overwrites_google_side_edits_and_removes_cancelled(client, auth, w, fake, db):
    a = create(client, auth, w)
    b = create(client, auth, w, day=3)
    run(fake)
    fake.events[(CAL, gcal_titles.event_id(a["id"]))]["summary"] = "被人改掉了"
    # b 在 Google 已有事件，但預約其實已取消且漏了入列
    db.execute(text("UPDATE appointments SET status = 'cancelled' WHERE id = :i"), {"i": b["id"]})
    db.commit()
    client.post("/settings/google/sync/resync", headers=auth(w["admin"]))
    run(fake, now=now_() + timedelta(minutes=5))
    assert ev(fake, a["id"])["summary"] == "諮商 · 2B · 王小明"  # 以 Cheerpsy 為準覆寫
    assert ev(fake, b["id"]) is None


def test_retry_requeues_blocked_and_failed_only(client, auth, w, fake, db):
    a = create(client, auth, w)
    b = create(client, auth, w, day=3)
    db.execute(text("UPDATE gcal_outbox SET status = 'blocked', last_error = 'x' WHERE appointment_id = :a"), {"a": a["id"]})
    db.commit()
    r = client.post("/settings/google/sync/retry", headers=auth(w["admin"]))
    assert r.status_code == 200
    assert job(db, a["id"]).status == "pending" and job(db, a["id"]).last_error is None and job(db, b["id"]).version == 1


def test_sync_status_permissions_and_no_case_data(client, auth, w, fake, db, make_user):
    a = create(client, auth, w)
    db.execute(text("UPDATE gcal_outbox SET status = 'failed', last_error = '壞了', attempts = 10 WHERE appointment_id = :a"), {"a": a["id"]})
    db.commit()
    for who, code in ((w["admin"], 200), (w["staff"], 200), (w["t"], 403), (make_user("accountant"), 403)):
        assert client.get("/settings/google/sync", headers=auth(who)).status_code == code
        assert client.post("/settings/google/sync/retry", headers=auth(who)).status_code in ((200, 409) if code == 200 else (403,))
    assert client.get("/settings/google/sync").status_code in (401, 403)
    body = client.get("/settings/google/sync", headers=auth(w["staff"])).json()
    blob = json.dumps(body, ensure_ascii=False)
    for secret in ("王小明", "0912", "C-1042"):
        assert secret not in blob
    assert body["can_resync"] is False and client.get("/settings/google/sync", headers=auth(w["admin"])).json()["can_resync"] is True


def test_oldest_due_reports_a_stuck_worker(client, auth, w, fake, db):
    a = create(client, auth, w)
    db.execute(text("UPDATE gcal_outbox SET next_attempt_at = now() - interval '10 minutes' WHERE appointment_id = :a"), {"a": a["id"]})
    db.commit()
    body = client.get("/settings/google/sync", headers=auth(w["admin"])).json()
    assert body["oldest_due_seconds"] >= 590 and body["counts"]["pending"] == 1


# ---------------------------------------------------------------------------
# 結構：migration、worker、compose
# ---------------------------------------------------------------------------
def test_migration_adds_only_its_tables_and_chain_is_linear():
    p = API_DIR / "alembic" / "versions" / "zl2b6c7d8e9f_gcal_outbox.py"
    txt = p.read_text(encoding="utf-8")
    assert 'down_revision = "zk1a5b6c7d8e"' in txt and txt.count("drop_table") == 2
    assert "alter_column" not in txt and "drop_column" not in txt
    others = [q.name for q in (API_DIR / "alembic" / "versions").glob("*.py") if 'down_revision = "zl2b6c7d8e9f"' in q.read_text(encoding="utf-8")]
    assert others == ["zm3c7d8e9f0a_gcal_title_name.py"]  # 後面只接標題格式 (d) 的 migration（鏈不分叉）


def test_migration_roundtrip(db):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    spec = importlib.util.spec_from_file_location("zl2b", API_DIR / "alembic" / "versions" / "zl2b6c7d8e9f_gcal_outbox.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def go(fn):
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            getattr(mod, fn)()

    tables = lambda: set(inspect(engine).get_table_names())  # noqa: E731
    before = tables() - {"gcal_outbox", "appointment_google_events"}
    db.rollback()
    try:
        go("downgrade")
        assert tables() == before and {"google_calendars", "appointments"} <= tables()
        go("upgrade")
        assert {"gcal_outbox", "appointment_google_events"} <= tables()
    finally:
        db.rollback()
        if "gcal_outbox" not in tables():
            go("upgrade")


def test_appointment_can_be_deleted_even_with_outbox_rows(client, auth, w, fake, db):
    a = create(client, auth, w)
    run(fake)
    assert client.request("DELETE", "/appointments", headers=auth(w["staff"]), json={"ids": [a["id"]]}).status_code == 200


def test_worker_entrypoint_and_compose_service():
    import app.gcal_worker as gw
    assert callable(gw.main)
    for name in ("docker-compose.yml", "docker-compose.prod.yml"):
        txt = (API_DIR.parents[1] / name).read_text(encoding="utf-8")
        if name == "docker-compose.prod.yml":
            assert "worker:" in txt and "app.gcal_worker" in txt and "GCAL_TOKEN_FERNET_KEY" in txt
            assert "GOOGLE_OAUTH_CLIENT_SECRET" in txt


def _load_zm():
    import importlib.util

    spec = importlib.util.spec_from_file_location("zm3c", API_DIR / "alembic" / "versions" / "zm3c7d8e9f0a_gcal_title_name.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _go(mod, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        getattr(mod, fn)()


def test_title_migration_only_changes_untouched_default_and_is_reversible(db, make_user):
    mod = _load_zm()
    admin = make_user("admin")
    db.rollback()
    try:
        _go(mod, "downgrade")  # 退回舊的三選一
        with pytest.raises(Exception):
            db.execute(text("INSERT INTO clinic_settings (id, event_title_format) VALUES (1, 'type_room_name')"))
        db.rollback()
        db.execute(text("INSERT INTO clinic_settings (id, event_title_format) VALUES (1, 'type_room_abbrev')"))
        db.commit()
        _go(mod, "upgrade")
        assert db.execute(text("SELECT event_title_format FROM clinic_settings")).scalar() == "type_room_name"  # 沒人動過的舊預設 → (d)
        db.rollback()
        _go(mod, "downgrade")
        assert db.execute(text("SELECT event_title_format FROM clinic_settings")).scalar() == "type_room_abbrev"
        db.execute(text("UPDATE clinic_settings SET updated_by_user_id = :u"), {"u": admin.id})  # 管理員明確選過 (c)
        db.commit()
        _go(mod, "upgrade")
        assert db.execute(text("SELECT event_title_format FROM clinic_settings")).scalar() == "type_room_abbrev"  # 不動
    finally:
        db.rollback()
        try:
            _go(mod, "upgrade")
        except Exception:
            pass
