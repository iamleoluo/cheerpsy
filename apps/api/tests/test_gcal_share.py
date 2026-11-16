"""Google 日曆同步 PR B：心理師日曆佈建與 ACL 分享。

全部不連外網：Calendar 用戶端換成記錄呼叫的 fake。重點：
- 分享名單 =（在職且有 Gmail 的心理師）∪ 行政名單 − 擁有者，去重，只寫差集。
- 擁有者不分享也不被刪；同一人兼心理師與行政時不重複、不誤刪。
- 更換信箱先取消舊的再分享新的；離職取消分享但日曆保留。
- staff 可管理對應表但不能改行政名單；心理師、會計一律 403。
"""

import importlib.util
import io
import json
import logging
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine
from app.models.gcal import GoogleCalendar, GoogleOAuthConnection
from app.models.user import User
from app.services import gcal_client, gcal_share, google_oauth
from app.services.gcal_client import (
    AclRule,
    CalendarApiError,
    CalendarInfo,
    GcalNotConnected,
    GoogleCalendarClient,
)

API_DIR = Path(__file__).resolve().parents[1]
OWNER = "clinic@gmail.com"


# ---------------------------------------------------------------------------
# Fake：記錄每一次呼叫，並在記憶體裡維護日曆與 ACL
# ---------------------------------------------------------------------------
class FakeCalendar:
    def __init__(self):
        self.calendars: dict[str, dict] = {}  # id -> {"summary", "acl": {rule_id: AclRule}}
        self.calls: list[tuple] = []
        self.fail: dict[str, CalendarApiError] = {}  # 方法名 -> 每次呼叫都丟這個錯
        self.fail_calendar: dict[str, CalendarApiError] = {}  # calendar id -> 對這本日曆的任何呼叫都丟錯
        self.deleted: set[str] = set()
        self.n = 0

    def _guard(self, name: str, cal_id: str | None = None):
        if name in self.fail:
            raise self.fail[name]
        if cal_id is not None:
            if cal_id in self.deleted or cal_id not in self.calendars:
                raise CalendarApiError(404, "notFound")
            if cal_id in self.fail_calendar:
                raise self.fail_calendar[cal_id]

    def create_calendar(self, summary, time_zone, description):
        self.calls.append(("create_calendar", summary, time_zone, description))
        self._guard("create_calendar")
        self.n += 1
        cid = f"cal{self.n}@group.calendar.google.com"
        self.calendars[cid] = {"summary": summary, "acl": {f"user:{OWNER}": AclRule(f"user:{OWNER}", "owner", "user", OWNER)}}
        return CalendarInfo(cid, summary)

    def rename_calendar(self, calendar_id, summary):
        self.calls.append(("rename_calendar", calendar_id, summary))
        self._guard("rename_calendar", calendar_id)
        self.calendars[calendar_id]["summary"] = summary

    def list_acl(self, calendar_id):
        self.calls.append(("list_acl", calendar_id))
        self._guard("list_acl", calendar_id)
        return list(self.calendars[calendar_id]["acl"].values())

    def insert_acl(self, calendar_id, email, role, send_notifications):
        self.calls.append(("insert_acl", calendar_id, email, role, send_notifications))
        self._guard("insert_acl", calendar_id)
        rule = AclRule(f"user:{email}", role, "user", email)
        self.calendars[calendar_id]["acl"][rule.rule_id] = rule
        return rule

    def patch_acl_role(self, calendar_id, rule_id, role):
        self.calls.append(("patch_acl_role", calendar_id, rule_id, role))
        self._guard("patch_acl_role", calendar_id)
        old = self.calendars[calendar_id]["acl"][rule_id]
        self.calendars[calendar_id]["acl"][rule_id] = AclRule(rule_id, role, old.scope_type, old.value)

    def delete_acl(self, calendar_id, rule_id):
        self.calls.append(("delete_acl", calendar_id, rule_id))
        self._guard("delete_acl", calendar_id)
        self.calendars[calendar_id]["acl"].pop(rule_id, None)

    # 測試輔助
    def ops(self, name):
        return [c for c in self.calls if c[0] == name]

    def shared(self, cal_id):  # 該日曆目前分享給誰（不含擁有者）
        return sorted(r.value for r in self.calendars[cal_id]["acl"].values() if r.role != "owner")

    def clear_calls(self):
        self.calls.clear()


@pytest.fixture()
def fake(monkeypatch, db):
    f = FakeCalendar()
    db.add(GoogleOAuthConnection(id=1, google_email=OWNER, status="active", refresh_token_enc="x",
                                 scopes=" ".join(google_oauth.CALENDAR_SCOPES)))
    db.commit()
    monkeypatch.setattr(gcal_client, "get_calendar_client", lambda _db: f)
    return f


@pytest.fixture()
def people(make_user):
    return dict(
        admin=make_user("admin"), staff=make_user("staff"),
        me=make_user("therapist"),
        a=make_user("therapist", name="王小明", gcal_share_email="a@gmail.com"),
        b=make_user("therapist", name="李大華", gcal_share_email="b@gmail.com", has_account=False),
    )


def H(auth, who):
    return auth(who)


def provision(client, auth, who, therapist):
    r = client.post(f"/settings/google/therapists/{therapist.id}/provision", headers=auth(who))
    assert r.status_code == 200, r.text
    return r.json()


def cal_row(db, therapist):
    db.expire_all()
    return db.query(GoogleCalendar).filter(GoogleCalendar.therapist_id == therapist.id).first()


def set_staff(client, auth, admin, emails):
    r = client.put("/settings/google/staff-emails", headers=auth(admin), json={"emails": emails})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 純函式：分享名單
# ---------------------------------------------------------------------------
def _t(email="A@Gmail.com", active=True):
    return User(name="x", email="x@x", password_hash="x", role="therapist", gcal_share_email=email, is_active=active)


def test_target_emails_is_union_normalized_and_deduped():
    row = GoogleCalendar(is_active=True)
    assert gcal_share.target_emails(_t(), row, [" a@gmail.com ", "S@x.org", "s@x.org"]) == {"a@gmail.com", "s@x.org"}
    assert gcal_share.target_emails(_t(), row, []) == {"a@gmail.com"}  # 心理師本人（轉小寫）
    assert gcal_share.target_emails(_t(email=None), row, ["s@x.org"]) == {"s@x.org"}
    assert gcal_share.target_emails(_t(email=""), row, []) == set()


def test_target_excludes_offboarded_or_frozen_therapist_but_keeps_staff():
    assert gcal_share.target_emails(_t(active=False), GoogleCalendar(is_active=True), ["s@x.org"]) == {"s@x.org"}
    assert gcal_share.target_emails(_t(), GoogleCalendar(is_active=False), ["s@x.org"]) == {"s@x.org"}
    # 同一人兼行政：離職後仍在行政名單 → 保留
    assert gcal_share.target_emails(_t(active=False), GoogleCalendar(is_active=True), ["a@gmail.com"]) == {"a@gmail.com"}


# ---------------------------------------------------------------------------
# sync_acl：只寫差集、擁有者、刪除先於新增
# ---------------------------------------------------------------------------
def _cal(fake):
    return fake.create_calendar("s", "Asia/Taipei", "d").id


def test_sync_acl_owner_is_skipped_and_never_deleted(fake):
    cid = _cal(fake)
    fake.clear_calls()
    res = gcal_share.sync_acl(fake, cid, {OWNER, "a@gmail.com"}, OWNER)
    assert fake.ops("insert_acl") == [("insert_acl", cid, "a@gmail.com", "reader", True)]  # 擁有者不 insert
    assert res.final == ["a@gmail.com"] and OWNER in res.owners
    fake.clear_calls()
    gcal_share.sync_acl(fake, cid, set(), OWNER)  # 名單清空：只刪 a，不碰擁有者
    assert fake.ops("delete_acl") == [("delete_acl", cid, "user:a@gmail.com")]
    assert OWNER in {r.value for r in fake.calendars[cid]["acl"].values()}


def test_sync_acl_owner_detected_from_acl_even_if_unknown_to_us(fake):
    cid = _cal(fake)
    fake.clear_calls()
    gcal_share.sync_acl(fake, cid, {OWNER}, None)  # 連線沒記 email，也要靠 acl.list 的 owner 項辨識
    assert fake.ops("insert_acl") == [] and fake.ops("delete_acl") == []


def test_sync_acl_writes_only_the_difference_and_is_idempotent(fake):
    cid = _cal(fake)
    gcal_share.sync_acl(fake, cid, {"a@gmail.com", "s@x.org"}, OWNER)
    fake.clear_calls()
    res = gcal_share.sync_acl(fake, cid, {"a@gmail.com", "s@x.org"}, OWNER)
    assert [c[0] for c in fake.calls] == ["list_acl"] and not res.added and not res.removed  # 第二次完全不寫
    fake.clear_calls()
    gcal_share.sync_acl(fake, cid, {"a@gmail.com", "n@x.org"}, OWNER)
    assert fake.ops("insert_acl") == [("insert_acl", cid, "n@x.org", "reader", True)]  # a 沒有重複寄邀請
    assert fake.ops("delete_acl") == [("delete_acl", cid, "user:s@x.org")]


def test_sync_acl_deletes_before_inserting(fake):
    cid = _cal(fake)
    gcal_share.sync_acl(fake, cid, {"old@gmail.com"}, OWNER)
    fake.clear_calls()
    gcal_share.sync_acl(fake, cid, {"new@gmail.com"}, OWNER)
    names = [c[0] for c in fake.calls if c[0] in ("delete_acl", "insert_acl")]
    assert names == ["delete_acl", "insert_acl"]


def test_sync_acl_fixes_wrong_role_and_removes_public_rules(fake):
    cid = _cal(fake)
    fake.calendars[cid]["acl"]["user:w@x.org"] = AclRule("user:w@x.org", "writer", "user", "w@x.org")
    fake.calendars[cid]["acl"]["default"] = AclRule("default", "reader", "default", "")  # 被誰設成公開
    fake.clear_calls()
    gcal_share.sync_acl(fake, cid, {"w@x.org"}, OWNER)
    assert fake.ops("patch_acl_role") == [("patch_acl_role", cid, "user:w@x.org", "reader")]
    assert fake.ops("delete_acl") == [("delete_acl", cid, "default")]  # 日曆含個案行程，不許公開
    assert fake.ops("insert_acl") == []


def test_sync_acl_ignores_404_on_delete(fake):
    cid = _cal(fake)
    gcal_share.sync_acl(fake, cid, {"a@gmail.com"}, OWNER)
    orig = fake.delete_acl

    def gone(calendar_id, rule_id):
        orig(calendar_id, rule_id)
        raise CalendarApiError(404, "notFound")

    fake.delete_acl = gone
    gcal_share.sync_acl(fake, cid, set(), OWNER)  # 不丟例外


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------
def test_provision_creates_calendar_and_shares_reader_with_notification(client, auth, people, fake, db):
    set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    d = provision(client, auth, people["staff"], people["a"])  # 行政也能操作
    assert fake.ops("create_calendar") == [("create_calendar", "王小明 · Cheerpsy", "Asia/Taipei", "由 Cheerpsy 同步，請勿在此修改。")]
    inserts = fake.ops("insert_acl")
    assert {(c[2], c[3], c[4]) for c in inserts} == {("a@gmail.com", "reader", True), ("desk@gmail.com", "reader", True)}
    assert all(c[4] is True for c in inserts)  # sendNotifications 不得為 false
    cid = list(fake.calendars)[0]
    assert fake.shared(cid) == ["a@gmail.com", "desk@gmail.com"]
    cal = d["calendar"]
    assert cal["share_status"] == "invited" and cal["shared_emails"] == ["a@gmail.com", "desk@gmail.com"]
    assert cal["is_active"] is True and cal["last_share_error"] is None
    assert "google_calendar_id" not in json.dumps(d)
    row = cal_row(db, people["a"])
    assert row.google_calendar_id == cid
    db.expire_all()
    ops = db.execute(text("SELECT string_agg(operation, ',') FROM audit_log WHERE table_name = 'google_calendars'")).scalar()
    assert "PROVISION" in ops
    assert "a@gmail.com" in str(db.execute(text("SELECT after_data FROM audit_log WHERE operation = 'PROVISION'")).scalar())  # 稽核有紀錄分享對象


def test_provision_twice_creates_nothing_new(client, auth, people, fake, db):
    provision(client, auth, people["admin"], people["a"])
    fake.clear_calls()
    d = provision(client, auth, people["admin"], people["a"])
    assert fake.ops("create_calendar") == [] and fake.ops("insert_acl") == [] and fake.ops("delete_acl") == []
    assert d["calendar"]["share_status"] == "invited"
    assert db.query(GoogleCalendar).count() == 1


def test_provision_without_therapist_email_shares_only_with_staff(client, auth, people, fake):
    set_staff(client, auth, people["admin"], [])
    t = people["me"]
    d = provision(client, auth, people["admin"], t)
    assert d["calendar"]["share_status"] == "not_shared" and d["calendar"]["shared_emails"] == []
    assert fake.ops("insert_acl") == []  # 沒有任何人可分享，日曆仍建好（空的）


def test_provision_therapist_email_equal_to_owner_is_not_shared(client, auth, people, fake, db):
    people["a"].gcal_share_email = OWNER.upper()
    db.add(people["a"])
    db.commit()
    d = provision(client, auth, people["admin"], people["a"])
    assert fake.ops("insert_acl") == []  # 擁有者已經看得到
    assert d["calendar"]["share_status"] == "owner" and d["calendar"]["shared_emails"] == []


def test_provision_requires_google_connection(client, auth, people, db):
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 409 and "連結" in r.json()["detail"]
    assert db.query(GoogleCalendar).count() == 0


def test_provision_validation(client, auth, people, fake, make_user, db):
    path = "/settings/google/therapists/{}/provision"
    assert client.post(path.format(people["staff"].id), headers=auth(people["admin"])).status_code == 404  # 不是心理師
    assert client.post(path.format(999999), headers=auth(people["admin"])).status_code == 404
    gone = make_user("therapist", is_active=False)
    r = client.post(path.format(gone.id), headers=auth(people["admin"]))
    assert r.status_code == 409 and "離職" in r.json()["detail"]
    assert fake.ops("create_calendar") == []


def test_provision_google_failure_stores_nothing(client, auth, people, fake, db):
    fake.fail["create_calendar"] = CalendarApiError(500, "backendError")
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 502 and "500" in r.json()["detail"]
    assert db.query(GoogleCalendar).count() == 0
    fake.fail["create_calendar"] = CalendarApiError(403, "rateLimitExceeded")
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 502 and "流量" in r.json()["detail"]


def test_provision_acl_failure_keeps_calendar_and_retry_does_not_duplicate(client, auth, people, fake, db):
    fake.fail["insert_acl"] = CalendarApiError(500, "backendError")
    d = provision(client, auth, people["admin"], people["a"])
    assert d["calendar"]["share_status"] == "error" and "500" in d["calendar"]["last_share_error"]
    assert len(fake.calendars) == 1 and cal_row(db, people["a"]) is not None  # 日曆 id 沒有遺失
    del fake.fail["insert_acl"]
    fake.clear_calls()
    d = provision(client, auth, people["admin"], people["a"])
    assert fake.ops("create_calendar") == [] and len(fake.calendars) == 1  # 重試不會再建第二本
    assert d["calendar"]["share_status"] == "invited" and d["calendar"]["last_share_error"] is None


def test_provision_throttle(client, auth, people, fake, db, make_user):
    now = datetime.now(timezone.utc)
    for i in range(gcal_share.MAX_CALENDARS_PER_HOUR):
        t = make_user("therapist")
        db.add(GoogleCalendar(therapist_id=t.id, google_calendar_id=f"x{i}", summary="s", created_at=now))
    db.commit()
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 429 and "60" in r.json()["detail"]
    assert fake.ops("create_calendar") == []
    db.query(GoogleCalendar).update({"created_at": now - timedelta(hours=2)})  # 超過一小時就不算
    db.commit()
    assert client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"])).status_code == 200


def test_provision_recreates_calendar_deleted_on_google(client, auth, people, fake, db):
    provision(client, auth, people["admin"], people["a"])
    first = list(fake.calendars)[0]
    fake.deleted.add(first)
    # 同步時發現日曆不在了 → 改信箱的自動佈建順便重建（沒有 Google 連結時才會停在「找不到」，見下）
    r = client.put(f"/settings/google/therapists/{people['a'].id}/email", headers=auth(people["admin"]), json={"email": "a2@gmail.com"})
    d = r.json()["calendar"]
    assert d["is_missing"] is False and d["share_status"] == "invited" and d["shared_emails"] == ["a2@gmail.com"]
    # 手動重建仍可用（已重建過則只是同步），仍只有一列
    d = provision(client, auth, people["admin"], people["a"])["calendar"]
    assert d["is_missing"] is False and d["share_status"] == "invited"
    assert cal_row(db, people["a"]).google_calendar_id != first and db.query(GoogleCalendar).count() == 1


# ---------------------------------------------------------------------------
# 更換信箱
# ---------------------------------------------------------------------------
def test_change_email_unshares_old_before_sharing_new(client, auth, people, fake, db):
    provision(client, auth, people["admin"], people["a"])
    cid = list(fake.calendars)[0]
    fake.clear_calls()
    r = client.put(f"/settings/google/therapists/{people['a'].id}/email", headers=auth(people["staff"]), json={"email": " New@Gmail.com "})
    assert r.status_code == 200 and r.json()["share_email"] == "new@gmail.com"
    steps = [c[:3] for c in fake.calls if c[0] in ("delete_acl", "insert_acl")]
    assert steps == [("delete_acl", cid, "user:a@gmail.com"), ("insert_acl", cid, "new@gmail.com")]  # 先舊後新
    assert fake.shared(cid) == ["new@gmail.com"]
    assert r.json()["calendar"]["shared_emails"] == ["new@gmail.com"]


def test_clear_email_removes_share_and_status(client, auth, people, fake):
    provision(client, auth, people["admin"], people["a"])
    cid = list(fake.calendars)[0]
    for blank in ("", None):
        r = client.put(f"/settings/google/therapists/{people['a'].id}/email", headers=auth(people["admin"]), json={"email": blank})
        assert r.status_code == 200 and r.json()["share_email"] is None
    assert fake.shared(cid) == [] and r.json()["calendar"]["share_status"] == "not_shared"


def test_email_validation_and_duplicates(client, auth, people, fake):
    url = f"/settings/google/therapists/{people['a'].id}/email"
    assert client.put(url, headers=auth(people["admin"]), json={"email": "nope"}).status_code == 422
    r = client.put(url, headers=auth(people["admin"]), json={"email": "B@gmail.com"})  # 已是李大華的
    assert r.status_code == 409 and "李大華" in r.json()["detail"]
    assert client.put(url, headers=auth(people["admin"]), json={"email": "a@gmail.com"}).status_code == 200  # 自己的不算重複


def test_email_saved_even_when_google_not_connected(client, auth, people, db, monkeypatch):
    t = people["me"]
    r = client.put(f"/settings/google/therapists/{t.id}/email", headers=auth(people["staff"]), json={"email": "me@gmail.com"})
    assert r.status_code == 200 and r.json()["share_email"] == "me@gmail.com" and r.json()["calendar"] is None  # 沒日曆、沒連結：只存
    # 已有日曆但之後授權失效：信箱照存，狀態標示尚未同步
    db.add(GoogleCalendar(therapist_id=t.id, google_calendar_id="c1", summary="s", share_status="invited"))
    db.commit()

    def boom(_db):
        raise GcalNotConnected("Google 授權已失效，請管理員重新連結", token_invalid=True)

    monkeypatch.setattr(gcal_client, "get_calendar_client", boom)
    r = client.put(f"/settings/google/therapists/{t.id}/email", headers=auth(people["admin"]), json={"email": "me2@gmail.com"})
    assert r.status_code == 200 and r.json()["share_email"] == "me2@gmail.com"
    assert r.json()["calendar"]["share_status"] == "error" and "尚未同步" in r.json()["calendar"]["last_share_error"]


# ---------------------------------------------------------------------------
# 填信箱後自動建立並分享（best-effort）
# ---------------------------------------------------------------------------
def _put_email(client, auth, who, t, email):
    return client.put(f"/settings/google/therapists/{t.id}/email", headers=auth(who), json={"email": email})


def test_setting_email_auto_provisions_and_shares(client, auth, people, fake, db):
    t = people["me"]
    r = _put_email(client, auth, people["staff"], t, "Me@Gmail.com")
    assert r.status_code == 200
    cal = r.json()["calendar"]
    assert cal is not None and cal["share_status"] == "invited" and cal["shared_emails"] == ["me@gmail.com"]
    assert len(fake.ops("create_calendar")) == 1
    assert fake.ops("insert_acl")[0][2:] == ("me@gmail.com", "reader", True)
    audit = db.execute(text("select operation from audit_log where table_name='google_calendars'")).scalars().all()
    assert "PROVISION" in audit


def test_auto_provision_is_idempotent_and_does_not_recreate(client, auth, people, fake):
    t = people["me"]
    _put_email(client, auth, people["admin"], t, "me@gmail.com")
    fake.clear_calls()
    r = _put_email(client, auth, people["admin"], t, "me@gmail.com")
    assert r.status_code == 200 and not fake.ops("create_calendar") and not fake.ops("insert_acl")
    r = _put_email(client, auth, people["admin"], t, "me2@gmail.com")  # 改信箱：只換分享，不新建日曆
    assert len(fake.ops("create_calendar")) == 0 and r.json()["calendar"]["shared_emails"] == ["me2@gmail.com"]


def test_auto_provision_failure_does_not_block_saving_email(client, auth, people, fake, db):
    t = people["me"]
    fake.fail["create_calendar"] = CalendarApiError(500, "backendError")
    r = _put_email(client, auth, people["staff"], t, "me@gmail.com")
    assert r.status_code == 200 and r.json()["share_email"] == "me@gmail.com" and r.json()["calendar"] is None
    assert cal_row(db, t) is None
    del fake.fail["create_calendar"]  # 手動補救
    assert provision(client, auth, people["staff"], t)["calendar"]["share_status"] == "invited"


def test_auto_provision_share_failure_marks_calendar_only(client, auth, people, fake, db):
    t = people["me"]
    fake.fail["insert_acl"] = CalendarApiError(500, "backendError")
    r = _put_email(client, auth, people["staff"], t, "me@gmail.com")
    assert r.status_code == 200 and r.json()["share_email"] == "me@gmail.com"
    assert r.json()["calendar"]["share_status"] == "error"
    assert cal_row(db, t) is not None  # 日曆 id 沒有遺失


def test_auto_provision_skipped_when_not_connected_or_cleared(client, auth, people, db, monkeypatch):
    t = people["me"]
    r = _put_email(client, auth, people["admin"], t, "me@gmail.com")  # 沒連結 Google
    assert r.status_code == 200 and r.json()["calendar"] is None


def test_clearing_email_does_not_provision(client, auth, people, fake):
    r = _put_email(client, auth, people["admin"], people["me"], "")
    assert r.status_code == 200 and not fake.ops("create_calendar")


def test_auto_provision_skips_offboarded_and_frozen(client, auth, people, fake, db):
    t = people["me"]
    t.is_active = False
    db.commit()
    assert _put_email(client, auth, people["admin"], t, "me@gmail.com").status_code == 200
    assert not fake.ops("create_calendar")
    # 取消分享（凍結）的日曆：改信箱不會自動恢復分享
    a = people["a"]
    provision(client, auth, people["admin"], a)
    client.post(f"/settings/google/therapists/{a.id}/unshare", headers=auth(people["admin"]))
    fake.clear_calls()
    r = _put_email(client, auth, people["admin"], a, "new@gmail.com")
    assert r.json()["calendar"]["is_active"] is False and not fake.ops("create_calendar")
    assert "new@gmail.com" not in fake.shared(list(fake.calendars)[0])


def test_auto_provision_recreates_missing_calendar(client, auth, people, fake, db):
    a = people["a"]
    provision(client, auth, people["admin"], a)
    fake.deleted.add(list(fake.calendars)[0])
    cal = cal_row(db, a)
    cal.is_missing = True
    db.commit()
    fake.clear_calls()
    r = _put_email(client, auth, people["admin"], a, "new@gmail.com")
    assert len(fake.ops("create_calendar")) == 1 and r.json()["calendar"]["is_missing"] is False


def test_roster_create_with_email_auto_provisions(client, auth, people, fake, db):
    r = client.post("/auth/roster-therapists", headers=auth(people["staff"]), json={"name": "新人", "gcal_share_email": "New@Gmail.com"})
    assert r.status_code == 201, r.text
    row = db.query(User).filter(User.id == r.json()["id"]).first()
    assert row.gcal_share_email == "new@gmail.com"
    cal = cal_row(db, row)
    assert cal is not None and cal.shared_emails == ["new@gmail.com"] and len(fake.ops("create_calendar")) == 1


def test_roster_create_without_email_or_google_still_works(client, auth, people, fake, db):
    r = client.post("/auth/roster-therapists", headers=auth(people["staff"]), json={"name": "無信箱"})
    assert r.status_code == 201 and not fake.ops("create_calendar")
    r = client.post("/auth/roster-therapists", headers=auth(people["staff"]), json={"name": "壞信箱", "gcal_share_email": "nope"})
    assert r.status_code == 400
    r = client.post("/auth/roster-therapists", headers=auth(people["staff"]), json={"name": "重複", "gcal_share_email": "a@gmail.com"})
    assert r.status_code == 409


def test_roster_create_succeeds_when_google_fails(client, auth, people, fake, db):
    fake.fail["create_calendar"] = CalendarApiError(500, "backendError")
    r = client.post("/auth/roster-therapists", headers=auth(people["staff"]), json={"name": "新人", "gcal_share_email": "n@gmail.com"})
    assert r.status_code == 201 and r.json()["name"] == "新人"


# ---------------------------------------------------------------------------
# 聯集：同一人兼心理師與行政
# ---------------------------------------------------------------------------
def test_person_who_is_both_therapist_and_staff_has_one_rule_and_is_never_wrongly_removed(client, auth, people, fake, db):
    a = people["a"]  # a@gmail.com
    set_staff(client, auth, people["admin"], ["a@gmail.com", "desk@gmail.com"])
    provision(client, auth, people["admin"], a)
    cid = list(fake.calendars)[0]
    assert [c[2] for c in fake.ops("insert_acl")].count("a@gmail.com") == 1  # 只有一筆 rule
    assert fake.shared(cid) == ["a@gmail.com", "desk@gmail.com"]

    # 從行政名單移除他：他仍是在職心理師 → 不能刪
    fake.clear_calls()
    set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    assert fake.ops("delete_acl") == [] and "a@gmail.com" in fake.shared(cid)

    # 再把他加回行政名單：不重複新增
    fake.clear_calls()
    set_staff(client, auth, people["admin"], ["a@gmail.com", "desk@gmail.com"])
    assert fake.ops("insert_acl") == [] and fake.ops("delete_acl") == []

    # 他離職、仍在行政名單 → 保留
    fake.clear_calls()
    r = client.put(f"/auth/users/{a.id}/toggle", headers=auth(people["admin"]))
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert fake.ops("delete_acl") == [] and "a@gmail.com" in fake.shared(cid)

    # 離職且不在行政名單 → 才刪
    set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    assert fake.shared(cid) == ["desk@gmail.com"]


# ---------------------------------------------------------------------------
# 取消分享／離職
# ---------------------------------------------------------------------------
def test_unshare_removes_therapist_only_and_keeps_calendar_and_staff(client, auth, people, fake, db):
    set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    provision(client, auth, people["admin"], people["a"])
    cid = list(fake.calendars)[0]
    r = client.post(f"/settings/google/therapists/{people['a'].id}/unshare", headers=auth(people["staff"]))
    assert r.status_code == 200
    cal = r.json()["calendar"]
    assert cal["share_status"] == "unshared" and cal["is_active"] is False and cal["shared_emails"] == ["desk@gmail.com"]
    assert fake.shared(cid) == ["desk@gmail.com"] and cid in fake.calendars  # 日曆保留、行政仍可看
    fake.clear_calls()
    assert client.post(f"/settings/google/therapists/{people['a'].id}/unshare", headers=auth(people["admin"])).status_code == 200
    assert fake.ops("delete_acl") == []  # 重複取消不再動 Google
    db.expire_all()
    assert "UNSHARE" in db.execute(text("SELECT string_agg(operation, ',') FROM audit_log WHERE table_name = 'google_calendars'")).scalar()


def test_unshare_without_calendar_is_404(client, auth, people, fake):
    r = client.post(f"/settings/google/therapists/{people['me'].id}/unshare", headers=auth(people["admin"]))
    assert r.status_code == 404


def test_provision_after_unshare_reshares_active_therapist(client, auth, people, fake):
    provision(client, auth, people["admin"], people["a"])
    client.post(f"/settings/google/therapists/{people['a'].id}/unshare", headers=auth(people["admin"]))
    d = provision(client, auth, people["admin"], people["a"])
    assert d["calendar"]["share_status"] == "invited" and d["calendar"]["is_active"] is True
    assert len(fake.calendars) == 1


def test_offboarding_via_roster_toggle_unshares_and_freezes_then_restores(client, auth, people, fake, db):
    provision(client, auth, people["admin"], people["b"])  # 名單制心理師（沒有登入帳號）
    cid = list(fake.calendars)[0]
    assert fake.shared(cid) == ["b@gmail.com"]
    r = client.put(f"/auth/users/{people['b'].id}/toggle", headers=auth(people["admin"]))
    assert r.status_code == 200 and r.json()["is_active"] is False
    row = cal_row(db, people["b"])
    assert row.is_active is False and row.share_status == "unshared" and fake.shared(cid) == []
    assert cid in fake.calendars  # 日曆不刪
    assert fake.ops("create_calendar") and len(fake.ops("create_calendar")) == 1
    # 恢復在職 → 重新分享
    r = client.put(f"/auth/users/{people['b'].id}/toggle", headers=auth(people["admin"]))
    assert r.json()["is_active"] is True
    row = cal_row(db, people["b"])
    assert row.is_active is True and row.share_status == "invited" and fake.shared(cid) == ["b@gmail.com"]


def test_offboarding_never_fails_when_google_is_down_or_disconnected(client, auth, people, fake, db, monkeypatch):
    provision(client, auth, people["admin"], people["a"])
    fake.fail["list_acl"] = CalendarApiError(500, "backendError")
    r = client.put(f"/auth/users/{people['a'].id}/toggle", headers=auth(people["admin"]))
    assert r.status_code == 200 and r.json()["is_active"] is False  # 名冊操作照常成功
    row = cal_row(db, people["a"])
    assert row.share_status == "error" and row.last_share_error and row.is_active is False  # 畫面會顯示失敗，可按取消分享重試
    # 之後 Google 恢復，按「取消分享」就能補上
    del fake.fail["list_acl"]
    client.post(f"/settings/google/therapists/{people['a'].id}/unshare", headers=auth(people["admin"]))
    assert cal_row(db, people["a"]).share_status == "unshared" and fake.shared(list(fake.calendars)[0]) == []

    def boom(_db):
        raise GcalNotConnected("尚未連結")

    monkeypatch.setattr(gcal_client, "get_calendar_client", boom)
    r = client.put(f"/auth/users/{people['a'].id}/toggle", headers=auth(people["admin"]))
    assert r.status_code == 200
    assert "尚未同步" in cal_row(db, people["a"]).last_share_error


def test_toggle_of_therapist_without_calendar_or_other_roles_touches_nothing(client, auth, people, fake):
    for who in (people["me"], people["staff"]):
        assert client.put(f"/auth/users/{who.id}/toggle", headers=auth(people["admin"])).status_code == 200
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 重寄邀請
# ---------------------------------------------------------------------------
def test_resend_invite_deletes_then_reinserts_with_notification(client, auth, people, fake):
    provision(client, auth, people["admin"], people["a"])
    cid = list(fake.calendars)[0]
    fake.clear_calls()
    r = client.post(f"/settings/google/therapists/{people['a'].id}/resend-invite", headers=auth(people["staff"]))
    assert r.status_code == 200
    steps = [c[:3] + c[3:] for c in fake.calls if c[0] in ("delete_acl", "insert_acl")]
    assert steps == [("delete_acl", cid, "user:a@gmail.com"), ("insert_acl", cid, "a@gmail.com", "reader", True)]
    assert r.json()["calendar"]["share_status"] == "invited"


def test_resend_invite_preconditions(client, auth, people, fake, db):
    url = "/settings/google/therapists/{}/resend-invite"
    assert client.post(url.format(people["a"].id), headers=auth(people["admin"])).status_code == 409  # 還沒有日曆
    provision(client, auth, people["admin"], people["me"])
    r = client.post(url.format(people["me"].id), headers=auth(people["admin"]))
    assert r.status_code == 409 and "Gmail" in r.json()["detail"]  # 沒填信箱
    people["a"].gcal_share_email = OWNER
    db.add(people["a"])
    db.commit()
    provision(client, auth, people["admin"], people["a"])
    r = client.post(url.format(people["a"].id), headers=auth(people["admin"]))
    assert r.status_code == 409 and "擁有者" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 行政名單
# ---------------------------------------------------------------------------
def test_staff_emails_permissions(client, auth, people, fake):
    for who in ("staff", "admin"):
        r = client.get("/settings/google/staff-emails", headers=auth(people[who]))
        assert r.status_code == 200 and r.json()["can_edit"] is (who == "admin") and r.json()["owner_email"] == OWNER
    assert client.put("/settings/google/staff-emails", headers=auth(people["staff"]), json={"emails": ["a@b.com"]}).status_code == 403
    for who in ("me",):
        assert client.get("/settings/google/staff-emails", headers=auth(people[who])).status_code == 403
        assert client.put("/settings/google/staff-emails", headers=auth(people[who]), json={"emails": []}).status_code == 403
    assert client.get("/settings/google/staff-emails").status_code in (401, 403)


def test_staff_emails_normalized_saved_and_validated(client, auth, people, fake):
    d = set_staff(client, auth, people["admin"], [" Desk@Gmail.com ", "desk@gmail.com", "b@x.org"])
    assert d["emails"] == ["desk@gmail.com", "b@x.org"] and d["synced"] == 0  # 還沒有日曆：只儲存
    assert client.get("/settings/google/staff-emails", headers=auth(people["staff"])).json()["emails"] == ["desk@gmail.com", "b@x.org"]
    assert client.get("/settings/clinic", headers=auth(people["admin"])).json()["staff_share_emails"] == ["desk@gmail.com", "b@x.org"]
    for bad in (["nope"], [""], ["a@b.com", "x"]):
        assert client.put("/settings/google/staff-emails", headers=auth(people["admin"]), json={"emails": bad}).status_code == 422


def test_staff_emails_change_syncs_every_calendar_with_differences_only(client, auth, people, fake):
    set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    provision(client, auth, people["admin"], people["a"])
    provision(client, auth, people["admin"], people["b"])
    c1, c2 = list(fake.calendars)
    fake.clear_calls()
    d = set_staff(client, auth, people["admin"], ["desk@gmail.com", "new@gmail.com"])
    assert d["synced"] == 2 and d["failed"] == 0
    assert sorted((c[1], c[2]) for c in fake.ops("insert_acl")) == sorted([(c1, "new@gmail.com"), (c2, "new@gmail.com")])
    assert fake.ops("delete_acl") == []  # desk 沒變，不重寄
    fake.clear_calls()
    set_staff(client, auth, people["admin"], ["new@gmail.com"])
    assert sorted(c[2] for c in fake.ops("delete_acl")) == ["user:desk@gmail.com", "user:desk@gmail.com"]
    assert fake.shared(c1) == ["a@gmail.com", "new@gmail.com"] and fake.shared(c2) == ["b@gmail.com", "new@gmail.com"]


def test_staff_emails_owner_is_skipped(client, auth, people, fake):
    provision(client, auth, people["admin"], people["a"])
    fake.clear_calls()
    set_staff(client, auth, people["admin"], [OWNER, "desk@gmail.com"])
    assert [c[2] for c in fake.ops("insert_acl")] == ["desk@gmail.com"]


def test_staff_emails_one_calendar_failing_does_not_block_others(client, auth, people, fake, db):
    provision(client, auth, people["admin"], people["a"])
    provision(client, auth, people["admin"], people["b"])
    c1, c2 = list(fake.calendars)
    fake.fail_calendar[c1] = CalendarApiError(500, "backendError")
    d = set_staff(client, auth, people["admin"], ["desk@gmail.com"])
    assert d["synced"] == 1 and d["failed"] == 1
    assert "desk@gmail.com" in fake.shared(c2)
    assert cal_row(db, people["a"]).share_status == "error" and cal_row(db, people["b"]).share_status == "invited"


def test_staff_emails_saved_when_not_connected(client, auth, people, db, monkeypatch):
    db.add(GoogleCalendar(therapist_id=people["a"].id, google_calendar_id="c1", summary="s"))
    db.commit()
    d = set_staff(client, auth, people["admin"], ["desk@gmail.com"])  # 沒有連線列、沒有 fake
    assert d["emails"] == ["desk@gmail.com"] and "尚未同步" in d["note"] and d["synced"] == 0


def test_clinic_patch_can_no_longer_change_staff_list(client, auth, people, fake):
    r = client.patch("/settings/clinic", headers=auth(people["admin"]), json={"staff_share_emails": ["x@y.com"]})
    assert r.status_code == 422
    assert client.get("/settings/clinic", headers=auth(people["admin"])).json()["staff_share_emails"] == []


# ---------------------------------------------------------------------------
# 對應表與權限
# ---------------------------------------------------------------------------
def test_list_therapists(client, auth, people, fake, make_user):
    gone_with_cal = make_user("therapist", name="離職有日曆", is_active=False)
    make_user("therapist", name="離職沒日曆", is_active=False)
    provision(client, auth, people["admin"], people["a"])
    client.post(f"/settings/google/therapists/{people['a'].id}/unshare", headers=auth(people["admin"]))
    from app.database import SessionLocal

    s = SessionLocal()
    s.add(GoogleCalendar(therapist_id=gone_with_cal.id, google_calendar_id="old", summary="s", is_active=False, share_status="unshared"))
    s.commit()
    s.close()
    for who in ("admin", "staff"):
        r = client.get("/settings/google/therapists", headers=auth(people[who]))
        assert r.status_code == 200
        names = {t["name"] for t in r.json()}
        assert {"王小明", "李大華", "離職有日曆"} <= names and "離職沒日曆" not in names  # 離職且沒日曆的不列
        assert "staff" not in {t["name"].split("-")[0] for t in r.json()}  # 不含非心理師
        a = next(t for t in r.json() if t["name"] == "王小明")
        assert a["share_email"] == "a@gmail.com" and a["calendar"]["share_status"] == "unshared"
        b = next(t for t in r.json() if t["name"] == "李大華")
        assert b["calendar"] is None and b["has_account"] is False
        assert "google_calendar_id" not in json.dumps(r.json())  # 內部 id 不外露
    assert client.get("/settings/google/therapists").status_code in (401, 403)


def test_therapist_cannot_use_any_calendar_endpoint(client, auth, people, fake):
    tid = people["a"].id
    for who in ("me",):
        h = auth(people[who])
        assert client.get("/settings/google/therapists", headers=h).status_code == 403
        assert client.put(f"/settings/google/therapists/{tid}/email", headers=h, json={"email": "z@z.com"}).status_code == 403
        for action in ("provision", "resend-invite", "unshare"):
            assert client.post(f"/settings/google/therapists/{tid}/{action}", headers=h).status_code == 403
    assert fake.calls == []
    for action in ("provision", "resend-invite", "unshare"):
        assert client.post(f"/settings/google/therapists/{tid}/{action}").status_code in (401, 403)


# ---------------------------------------------------------------------------
# 連線狀態：授權失效、缺 scope
# ---------------------------------------------------------------------------
@pytest.fixture()
def real_conn(db, monkeypatch):
    from app.services import secret_box

    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/cb")
    db.add(GoogleOAuthConnection(id=1, google_email=OWNER, status="active", refresh_token_enc=secret_box.encrypt("REFRESH-SECRET"),
                                 scopes=" ".join(google_oauth.CALENDAR_SCOPES)))
    db.commit()


def test_invalid_grant_marks_connection_invalid_and_returns_409(client, auth, people, real_conn, db, monkeypatch):
    def refresh(self, token):
        assert token == "REFRESH-SECRET"  # 解密後才送給 Google
        raise google_oauth.GoogleOAuthError("invalid_grant")

    monkeypatch.setattr(google_oauth.GoogleOAuthClient, "refresh_access_token", refresh)
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 409 and "重新連結" in r.json()["detail"]
    db.expire_all()
    conn = db.get(GoogleOAuthConnection, 1)
    assert conn.status == "token_invalid" and conn.token_invalid_at is not None and conn.last_error_code == "invalid_grant"
    # 狀態已是 token_invalid：之後不再打 Google
    monkeypatch.setattr(google_oauth.GoogleOAuthClient, "refresh_access_token", lambda s, t: pytest.fail("不該再呼叫"))
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 409
    assert client.get("/settings/clinic", headers=auth(people["staff"])).json()["connection"]["status"] == "token_invalid"


def test_missing_calendar_scope_is_rejected(client, auth, people, real_conn, db):
    db.get(GoogleOAuthConnection, 1).scopes = google_oauth.CALENDAR_SCOPES[0]
    db.commit()
    r = client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    assert r.status_code == 409 and "權限" in r.json()["detail"]


def test_disconnected_status_rejects_actions(client, auth, people, real_conn, db):
    db.get(GoogleOAuthConnection, 1).status = "disconnected"
    db.commit()
    assert client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"])).status_code == 409


def test_success_updates_last_success_and_logs_have_no_tokens(client, auth, people, fake, db, caplog):
    caplog.set_level(logging.DEBUG)
    provision(client, auth, people["admin"], people["a"])
    db.expire_all()
    assert db.get(GoogleOAuthConnection, 1).last_success_at is not None
    fake.fail["list_acl"] = CalendarApiError(500, "backendError")
    client.post(f"/settings/google/therapists/{people['a'].id}/provision", headers=auth(people["admin"]))
    text_ = "\n".join(r.getMessage() for r in caplog.records)
    assert "a@gmail.com" not in text_ and "Bearer" not in text_  # log 不含信箱與憑證


# ---------------------------------------------------------------------------
# 真正的 HTTP 用戶端（urlopen 以 stub 取代，不連外網）
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, body: dict):
        self._b = json.dumps(body).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def http(monkeypatch):
    seen: list[dict] = []
    queue: list = []

    def fake_urlopen(req, timeout=None):
        seen.append({"method": req.get_method(), "url": req.full_url, "body": json.loads(req.data) if req.data else None,
                     "auth": req.get_header("Authorization")})
        item = queue.pop(0) if queue else {}
        if isinstance(item, Exception):
            raise item
        return _Resp(item)

    monkeypatch.setattr(gcal_client.urllib.request, "urlopen", fake_urlopen)
    return seen, queue


def test_http_client_request_shapes(http):
    seen, queue = http
    c = GoogleCalendarClient("ACCESS-TOKEN")
    queue.append({"id": "c1@group.calendar.google.com", "summary": "王 · Cheerpsy"})
    info = c.create_calendar("王 · Cheerpsy", "Asia/Taipei", "d")
    assert info == CalendarInfo("c1@group.calendar.google.com", "王 · Cheerpsy")
    assert seen[-1]["method"] == "POST" and seen[-1]["url"].endswith("/calendars")
    assert seen[-1]["body"] == {"summary": "王 · Cheerpsy", "timeZone": "Asia/Taipei", "description": "d"}
    assert seen[-1]["auth"] == "Bearer ACCESS-TOKEN"

    queue.append({"id": "user:a@gmail.com", "role": "reader", "scope": {"type": "user", "value": "A@Gmail.com"}})
    rule = c.insert_acl("c1@group.calendar.google.com", "a@gmail.com", "reader", True)
    assert rule == AclRule("user:a@gmail.com", "reader", "user", "a@gmail.com")
    assert seen[-1]["method"] == "POST" and "sendNotifications=true" in seen[-1]["url"]
    assert "/calendars/c1%40group.calendar.google.com/acl?" in seen[-1]["url"]  # calendar id 要 URL 編碼
    assert seen[-1]["body"] == {"role": "reader", "scope": {"type": "user", "value": "a@gmail.com"}}

    queue.append({})
    c.delete_acl("c1@group.calendar.google.com", "user:a@gmail.com")
    assert seen[-1]["method"] == "DELETE" and seen[-1]["url"].endswith("/acl/user%3Aa%40gmail.com")

    queue.append({})
    c.patch_acl_role("c1@group.calendar.google.com", "user:a@gmail.com", "reader")
    assert seen[-1]["method"] == "PATCH" and "sendNotifications=false" in seen[-1]["url"]
    queue.append({})
    c.rename_calendar("c1@group.calendar.google.com", "新名")
    assert seen[-1]["method"] == "PATCH" and seen[-1]["body"] == {"summary": "新名"}


def test_http_client_list_acl_paginates(http):
    seen, queue = http
    queue.append({"items": [{"id": "o", "role": "owner", "scope": {"type": "user", "value": OWNER}}], "nextPageToken": "P2"})
    queue.append({"items": [{"id": "d", "role": "reader", "scope": {"type": "default"}}]})
    rules = GoogleCalendarClient("t").list_acl("c@g")
    assert [r.rule_id for r in rules] == ["o", "d"] and rules[1].scope_type == "default" and rules[1].value == ""
    assert "pageToken=P2" in seen[-1]["url"]


def test_http_client_errors_carry_status_and_reason_only(http):
    seen, queue = http
    body = io.BytesIO(json.dumps({"error": {"errors": [{"reason": "rateLimitExceeded"}], "message": "a@gmail.com SECRET"}}).encode())
    queue.append(urllib.error.HTTPError("u", 403, "x", {}, body))
    with pytest.raises(CalendarApiError) as e:
        GoogleCalendarClient("ACCESS-TOKEN").list_acl("c")
    assert (e.value.status, e.value.reason) == (403, "rateLimitExceeded")
    assert "ACCESS-TOKEN" not in str(e.value) and "SECRET" not in str(e.value) and "a@gmail.com" not in str(e.value)
    queue.append(urllib.error.URLError("down"))
    with pytest.raises(CalendarApiError) as e:
        GoogleCalendarClient("t").list_acl("c")
    assert e.value.status == 0


def test_refresh_access_token_request_and_errors(monkeypatch):
    sent = {}

    def ok(req, timeout=None):
        sent["body"] = req.data.decode()
        sent["url"] = req.full_url
        return _Resp({"access_token": "AT", "expires_in": 3599})

    monkeypatch.setattr(google_oauth.urllib.request, "urlopen", ok)
    cl = google_oauth.GoogleOAuthClient("cid", "csecret", "http://x/cb")
    assert cl.refresh_access_token("RT") == "AT"
    assert sent["url"] == google_oauth.TOKEN_URL and "grant_type=refresh_token" in sent["body"] and "refresh_token=RT" in sent["body"]

    monkeypatch.setattr(google_oauth.urllib.request, "urlopen", lambda req, timeout=None: _Resp({}))
    with pytest.raises(google_oauth.GoogleOAuthError):
        cl.refresh_access_token("RT")  # 沒給 access_token


# ---------------------------------------------------------------------------
# 資料表與 migration
# ---------------------------------------------------------------------------
def test_google_calendar_constraints(db, make_user):
    from sqlalchemy.exc import IntegrityError

    t = make_user("therapist")
    db.add(GoogleCalendar(therapist_id=t.id, google_calendar_id="c1", summary="s"))
    db.commit()
    for kw in (dict(google_calendar_id="c2"), ):  # 同一位心理師只能有一本
        db.add(GoogleCalendar(therapist_id=t.id, summary="s", **kw))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    t2 = make_user("therapist")
    db.add(GoogleCalendar(therapist_id=t2.id, google_calendar_id="c1", summary="s"))  # 同一個 Google 日曆不能對到兩位
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(GoogleCalendar(therapist_id=t2.id, google_calendar_id="c3", summary="s", share_status="weird"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def _mig():
    path = API_DIR / "alembic" / "versions" / "zk1a5b6c7d8e_gcal_calendars.py"
    spec = importlib.util.spec_from_file_location("zk1a5b6c7d8e", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(_mig(), fn)()


def _cols(table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_roundtrip_touches_only_its_own_objects(db, make_user):
    make_user("admin", gcal_share_email=None)
    before_tables = set(inspect(engine).get_table_names()) - {"google_calendars"}
    before_user_cols = _cols("users") - {"gcal_share_email"}
    db.rollback()
    try:
        _run("downgrade")
        assert "google_calendars" not in inspect(engine).get_table_names() and "gcal_share_email" not in _cols("users")
        assert set(inspect(engine).get_table_names()) == before_tables and _cols("users") == before_user_cols
        assert {"clinic_settings", "google_oauth_connections"} <= set(inspect(engine).get_table_names())  # PR A 的表不受影響
        assert db.execute(text("SELECT count(*) FROM users")).scalar() == 1  # 既有資料還在
        db.rollback()
        _run("upgrade")
        assert "google_calendars" in inspect(engine).get_table_names() and "gcal_share_email" in _cols("users")
        assert db.execute(text("SELECT count(*) FROM users")).scalar() == 1
    finally:
        db.rollback()
        if "google_calendars" not in inspect(engine).get_table_names():
            _run("upgrade")


@pytest.mark.real_commit
@pytest.mark.slow
def test_migration_chain_and_only_adds():
    txt = (API_DIR / "alembic" / "versions" / "zk1a5b6c7d8e_gcal_calendars.py").read_text(encoding="utf-8")
    assert 'down_revision = "zj0f4a5b6c7d"' in txt
    children = [p.name for p in (API_DIR / "alembic" / "versions").glob("*.py")
                if 'down_revision = "zk1a5b6c7d8e"' in p.read_text(encoding="utf-8")]
    assert children == ["zl2b6c7d8e9f_gcal_outbox.py"]  # 後面只接 PR C 的 migration（鏈不分叉）
    assert txt.count("drop_table") == 1 and txt.count("drop_column") == 1 and "DELETE" not in txt.upper().replace("DELETE_", "")
    assert "alter_column" not in txt
