"""iCal feed 隱私：feed 網址即權限，內容不可含任何個案資訊。"""

from datetime import datetime, timedelta, timezone

import pytest

CLIENT_NAME = "王小明"
CLIENT_PHONE = "0912-345-678"
COMPLAINT = "憂鬱與失眠"


@pytest.fixture()
def therapist(make_user, db):
    t = make_user("therapist", name="林心理師")
    t.ical_token = "tok-ical-test-123"
    db.commit()
    return t


def _feed(client, token="tok-ical-test-123") -> str:
    r = client.get(f"/calendar/{token}.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    return r.text.replace("\r\n ", "")  # 解開折行


def test_unknown_token_404(client):
    assert client.get("/calendar/nope.ics").status_code == 404


def test_feed_has_no_client_information(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME, institution_id=None, referral_source="某某機構")
    make_appt(case, therapist, room)
    body = _feed(client)

    assert "BEGIN:VEVENT" in body
    for secret in (CLIENT_NAME, CLIENT_PHONE, COMPLAINT, "某某機構", "1500"):
        assert secret not in body


def test_summary_is_type_and_room_code(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME)
    make_appt(case, therapist, room)
    body = _feed(client)
    assert "SUMMARY:諮商 · 2B" in body
    assert "DESCRIPTION:Cheerpsy" in body
    assert "LOCATION:2B" in body


def test_intake_online_outdoor_labels(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME)
    make_appt(case, therapist, room, is_intake=True)
    make_appt(case, therapist, None, session_type="online")
    make_appt(case, therapist, None, session_type="outdoor")
    body = _feed(client)
    assert "SUMMARY:初診 · 2B" in body
    assert "SUMMARY:線上諮商" in body
    assert "SUMMARY:外展" in body
    assert "LOCATION:線上" in body
    assert "LOCATION:外展" in body
    assert CLIENT_NAME not in body


def test_intake_without_case_does_not_crash(client, therapist, room, make_appt):
    make_appt(None, therapist, room, is_intake=True)
    assert "SUMMARY:初診 · 2B" in _feed(client)


def test_uid_format_stable(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME)
    a = make_appt(case, therapist, room)
    assert f"UID:cheerpsy-appt-{a.id}@cheerpsy" in _feed(client)


def test_cancelled_and_no_show_emitted_as_cancelled(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME)
    ok = make_appt(case, therapist, room, status="booked")
    cancelled = make_appt(case, therapist, room, status="cancelled")
    absent = make_appt(case, therapist, room, status="no_show")
    body = _feed(client)

    def block(appt_id: int) -> str:
        start = body.index(f"UID:cheerpsy-appt-{appt_id}@cheerpsy")
        return body[start: body.index("END:VEVENT", start)]

    assert "STATUS:CONFIRMED" in block(ok.id)
    assert "STATUS:CANCELLED" in block(cancelled.id)
    assert "STATUS:CANCELLED" in block(absent.id)
    assert CLIENT_NAME not in body


def test_cancelled_older_than_90_days_dropped(client, therapist, room, make_case, make_appt):
    case = make_case(therapist, CLIENT_NAME)
    now = datetime.now(timezone.utc)
    old = make_appt(case, therapist, room, status="cancelled", start=now - timedelta(days=120))
    recent = make_appt(case, therapist, room, status="cancelled", start=now - timedelta(days=30))
    body = _feed(client)
    assert f"cheerpsy-appt-{old.id}@" not in body
    assert f"cheerpsy-appt-{recent.id}@" in body


def test_only_own_appointments(client, therapist, room, make_user, make_case, make_appt):
    other = make_user("therapist")
    other_case = make_case(other, "別人的個案")
    theirs = make_appt(other_case, other, room)
    body = _feed(client)
    assert f"cheerpsy-appt-{theirs.id}@" not in body
    assert "別人的個案" not in body
