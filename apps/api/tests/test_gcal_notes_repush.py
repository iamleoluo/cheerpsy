"""事件說明欄的「給心理師的提醒」（PR D）與單一心理師重新推送（PR E）。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.gcal import AppointmentGoogleEvent, GcalOutbox, GoogleOAuthConnection
from app.services import gcal_push, gcal_titles


@pytest.fixture()
def world(make_user, make_case, make_appt, room, db):
    a = make_user("therapist", name="甲心理師", gcal_share_email="a@gmail.com")
    b = make_user("therapist", name="乙心理師")
    ca = make_case(a, "王小明", phone="0912-345-678", chief_complaint="憂鬱與失眠")
    cb = make_case(b, "乙的個案")
    db.add(GoogleOAuthConnection(id=1, status="active", scopes="", refresh_token_enc="x"))
    db.commit()
    return dict(a=a, b=b, ca=ca, cb=cb, staff=make_user("staff"), admin=make_user("admin"), room=room,
                make_appt=make_appt)


# ---------------------------------------------------------------- 說明欄
def test_description_reminder_fields_in_person(world):
    w = world
    a = w["make_appt"](w["ca"], w["a"], w["room"], session_type="in_person")
    d = gcal_titles.event_description(a)
    assert "【給心理師的提醒】" in d and "類型：現場" in d and f"診間：{w['room'].room_code}" in d and "初診：否" in d
    assert "方案" not in d and "自負額" not in d  # 自費不顯示方案與自負額


def test_description_online_outdoor_and_intake(world):
    w = world
    on = w["make_appt"](w["ca"], w["a"], None, session_type="online", is_intake=True)
    d = gcal_titles.event_description(on)
    assert "類型：視訊" in d and "診間" not in d and "初診：是" in d
    out = w["make_appt"](w["ca"], w["a"], None, session_type="outdoor")
    assert "類型：外展" in gcal_titles.event_description(out)


@pytest.mark.parametrize("value,expect", [(None, "自負額：未設定"), (0, "自負額：0（全額補助）"), (200, "自負額：200 元")])
def test_description_institution_plan_and_self_pay(world, value, expect):
    w = world
    a = w["make_appt"](w["ca"], w["a"], w["room"])
    a.funding_source, a.self_pay_amount = "institution", value
    d = gcal_titles.event_description(a, plan_name="家扶中心方案")
    assert "方案：家扶中心方案" in d and expect in d
    assert "方案：未設定" in gcal_titles.event_description(a)  # 沒帶方案名稱


def test_description_has_no_sensitive_data(world):
    w = world
    a = w["make_appt"](w["ca"], w["a"], w["room"])
    a.funding_source, a.self_pay_amount = "institution", 200
    body = gcal_titles.event_body(a, "type_room", plan_name="某方案")
    d = body["description"]
    for secret in ("0912", "憂鬱", "王小明", "甲心理師", "乙心理師", "a@gmail.com", "@", "$", a.appointment_number):
        assert secret not in d, secret
    assert body["summary"] == gcal_titles.event_title(a, "type_room")  # 標題格式不變


def test_push_reads_only_the_plan_name(world, db):
    w = world
    a = w["make_appt"](w["ca"], w["a"], w["room"])
    assert gcal_push._plan_name(db, a) is None  # 沒有方案


# ---------------------------------------------------------------- repush
def future(days):
    return datetime.now(timezone.utc) + timedelta(days=days)


def queued_ids(db):
    return {r.appointment_id for r in db.query(GcalOutbox).all()}


def repush(client, auth, who, tid):
    return client.post(f"/gcal/therapists/{tid}/repush", headers=auth(who))


def test_repush_only_that_therapists_future_booked(client, auth, world, db):
    w = world
    f1 = w["make_appt"](w["ca"], w["a"], w["room"], start=future(3))
    f2 = w["make_appt"](w["ca"], w["a"], w["room"], start=future(4))
    past = w["make_appt"](w["ca"], w["a"], w["room"], start=future(-3))
    cancelled = w["make_appt"](w["ca"], w["a"], w["room"], start=future(5), status="cancelled")
    other = w["make_appt"](w["cb"], w["b"], w["room"], start=future(6))
    db.query(GcalOutbox).delete()
    db.add(AppointmentGoogleEvent(appointment_id=f1.id, google_calendar_id="c", google_event_id="e",
                                  payload_hash="oldhash", last_status="pushed"))
    db.commit()
    r = repush(client, auth, w["staff"], w["a"].id)
    assert r.status_code == 200, r.text
    assert r.json()["queued"] == 2 and r.json()["already_queued"] == 0
    assert queued_ids(db) == {f1.id, f2.id}  # 過去、已取消、別的心理師都不動
    assert past.id not in queued_ids(db) and cancelled.id not in queued_ids(db) and other.id not in queued_ids(db)
    db.expire_all()
    assert db.get(AppointmentGoogleEvent, f1.id).payload_hash == ""  # 清掉雜湊：強制覆寫


def test_repush_is_idempotent_and_skips_already_queued(client, auth, world, db):
    w = world
    w["make_appt"](w["ca"], w["a"], w["room"], start=future(3))
    w["make_appt"](w["ca"], w["a"], w["room"], start=future(4))
    db.query(GcalOutbox).delete()
    db.commit()
    assert repush(client, auth, w["admin"], w["a"].id).json()["queued"] == 2
    version = {r.appointment_id: r.version for r in db.query(GcalOutbox).all()}
    again = repush(client, auth, w["admin"], w["a"].id).json()
    assert again["queued"] == 0 and again["already_queued"] == 2
    db.expire_all()
    assert db.query(GcalOutbox).count() == 2
    assert {r.appointment_id: r.version for r in db.query(GcalOutbox).all()} == version  # 沒被重設
    # 處理完（done）之後可以再排
    for r in db.query(GcalOutbox).all():
        r.status = "done"
    db.commit()
    assert repush(client, auth, w["admin"], w["a"].id).json()["queued"] == 2


def test_repush_forbidden_for_therapist_and_404_for_non_therapist(client, auth, world):
    w = world
    assert repush(client, auth, w["a"], w["a"].id).status_code == 403
    assert repush(client, auth, w["b"], w["a"].id).status_code == 403
    assert repush(client, auth, w["admin"], w["staff"].id).status_code == 404
    assert repush(client, auth, w["admin"], 999999).status_code == 404
    assert client.post(f"/gcal/therapists/{w['a'].id}/repush").status_code in (401, 403)
