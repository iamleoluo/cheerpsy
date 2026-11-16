"""GET /gcal/my-status：心理師只看到自己的同步狀態；三種情況；非心理師 403；不洩漏原始錯誤或他人資料。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.gcal import AppointmentGoogleEvent, GcalOutbox, GoogleCalendar, GoogleOAuthConnection

SECRET = "refresh-token-SECRET-xyz"


@pytest.fixture()
def world(make_user, make_case, make_appt, room):
    a = make_user("therapist", name="甲心理師", gcal_share_email="a@gmail.com")
    b = make_user("therapist", name="乙心理師", gcal_share_email="b@gmail.com")
    return dict(a=a, b=b, staff=make_user("staff"), admin=make_user("admin"), room=room,
                ca=make_case(a, "甲的個案"), cb=make_case(b, "乙的個案"), make_appt=make_appt)


def connect(db, status="active"):
    db.add(GoogleOAuthConnection(id=1, status=status, scopes="", refresh_token_enc=SECRET))
    db.commit()


def calendar(db, t, **kw):
    c = GoogleCalendar(therapist_id=t.id, google_calendar_id=f"cal-{t.id}", summary=f"cal {t.id}", **kw)
    db.add(c)
    db.commit()
    return c


def outbox(db, appt, status, err=None):
    """預約建立時掛鉤可能已入列同一個 dedupe_key，所以有就改、沒有才新增。"""
    row = db.query(GcalOutbox).filter(GcalOutbox.dedupe_key == f"appt:{appt.id}").first()
    if row is None:
        row = GcalOutbox(job_type="upsert_event", appointment_id=appt.id, dedupe_key=f"appt:{appt.id}")
        db.add(row)
    row.status, row.last_error = status, err
    db.commit()


def status(client, auth, who):
    r = client.get("/gcal/my-status", headers=auth(who))
    assert r.status_code == 200, r.text
    return r.json()


def test_not_connected(client, auth, world):
    s = status(client, auth, world["a"])
    assert s["clinic_connected"] is False and s["calendar_created"] is False and s["shared_to_me"] is False
    assert s["problem"] == "診所尚未連上 Google" and s["failed_count"] == 0 and s["pending_count"] == 0
    assert s["last_push_at"] is None


def test_token_invalid_is_reported(client, auth, world, db):
    connect(db, "token_invalid")
    s = status(client, auth, world["a"])
    assert s["clinic_connected"] is False and "授權已失效" in s["problem"]


def test_connected_but_no_calendar(client, auth, world, db):
    connect(db)
    s = status(client, auth, world["a"])
    assert s["clinic_connected"] is True and s["calendar_created"] is False and s["shared_to_me"] is False
    assert "尚未建立" in s["problem"]


def test_calendar_shared_ok(client, auth, world, db):
    connect(db)
    calendar(db, world["a"], share_status="invited")
    s = status(client, auth, world["a"])
    assert s["calendar_created"] and s["shared_to_me"] and s["problem"] is None and s["share_email"] == "a@gmail.com"


def test_failures_pending_and_last_push_counted_for_me_only(client, auth, world, db):
    w = world
    connect(db)
    calendar(db, w["a"], share_status="owner")
    t0 = datetime.now(timezone.utc) - timedelta(days=5)
    a1 = w["make_appt"](w["ca"], w["a"], w["room"], start=t0)
    a2 = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 + timedelta(hours=3))
    a3 = w["make_appt"](w["ca"], w["a"], w["room"], start=t0 + timedelta(hours=6))
    b1 = w["make_appt"](w["cb"], w["b"], w["room"], start=t0 + timedelta(hours=9))
    pushed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.add_all([
        AppointmentGoogleEvent(appointment_id=a1.id, google_calendar_id="c", google_event_id="e", payload_hash="h",
                               last_pushed_at=pushed_at, last_status="pushed"),
        AppointmentGoogleEvent(appointment_id=b1.id, google_calendar_id="c", google_event_id="e2", payload_hash="h",
                               last_pushed_at=datetime.now(timezone.utc), last_status="pushed"),  # 別人的，較新
    ])
    db.commit()
    outbox(db, a1, "done")
    outbox(db, a2, "failed", f"Google 拒絕這個操作（授權或權限不足） {SECRET}")
    outbox(db, a3, "retry")
    outbox(db, b1, "failed", "乙的個案 私密錯誤")
    s = status(client, auth, w["a"])
    assert s["failed_count"] == 1 and s["pending_count"] == 1
    assert s["last_push_at"].startswith(pushed_at.strftime("%Y-%m-%dT%H:%M")[:13])  # 自己的，不是乙的較新時間
    assert s["problem"] == "權限問題，請通知管理員檢查 Google 連線"
    text = str(s)
    for bad in (SECRET, "乙", "私密錯誤", "授權或權限不足"):
        assert bad not in text
    # 乙看到的是乙自己的
    sb = status(client, auth, w["b"])
    assert sb["failed_count"] == 1 and sb["pending_count"] == 0 and sb["share_email"] == "b@gmail.com"


@pytest.mark.parametrize("raw,expect", [
    ("無法連線到 Google，請稍後再試", "網路問題"),
    ("Google 流量限制，請稍後再試", "流量限制"),
    ("Google 上找不到這本日曆", "找不到"),
    ("其他奇怪的錯誤 abc", "同步發生錯誤"),
])
def test_calendar_share_error_is_summarised(client, auth, world, db, raw, expect):
    connect(db)
    calendar(db, world["a"], share_status="error", last_share_error=raw)
    s = status(client, auth, world["a"])
    assert expect in s["problem"] and raw not in s["problem"]


def test_missing_calendar(client, auth, world, db):
    connect(db)
    calendar(db, world["a"], share_status="error", is_missing=True)
    s = status(client, auth, world["a"])
    assert s["shared_to_me"] is False and "找不到" in s["problem"]


@pytest.mark.parametrize("role", ["staff", "admin"])
def test_non_therapist_forbidden(client, auth, world, role):
    assert client.get("/gcal/my-status", headers=auth(world[role])).status_code == 403


def test_requires_login(client):
    assert client.get("/gcal/my-status").status_code in (401, 403)
