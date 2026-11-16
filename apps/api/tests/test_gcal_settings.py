"""Google 日曆同步 PR A：診所設定、OAuth 連線、refresh token 加密。

全部不連外網：Google 用戶端以 fake 取代。重點：
- 只有 admin 能連結／解除連結／改設定；staff 只能讀。
- refresh token 以密文入庫，不出現在任何回應、redirect、log、稽核紀錄。
- state 簽章防偽、過期、被盜用；少一個 scope 不存半套授權。
"""

import importlib.util
import json
import logging
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from jose import jwt
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import engine
from app.routers import gcal_settings as gs
from app.services import google_oauth, secret_box
from app.services.google_oauth import (
    CALENDAR_SCOPES,
    GoogleOAuthClient,
    GoogleOAuthError,
    TokenResult,
)

API_DIR = Path(__file__).resolve().parents[1]
REFRESH = "1//0g-REFRESH-TOKEN-SECRET"
CODE = "4/0AX4-AUTH-CODE-SECRET"
ALL_SCOPES = " ".join(CALENDAR_SCOPES) + " openid https://www.googleapis.com/auth/userinfo.email"


class FakeClient(GoogleOAuthClient):
    def __init__(self, tokens=None, exchange_error=None, revoke_error=None):
        super().__init__("test-client-id", "test-client-secret", "http://localhost:8000/settings/google/callback")
        self.tokens = tokens or TokenResult(refresh_token=REFRESH, scope=ALL_SCOPES, email="clinic@gmail.com")
        self.exchange_error, self.revoke_error = exchange_error, revoke_error
        self.codes: list[str] = []
        self.revoked: list[str] = []

    def exchange_code(self, code):
        self.codes.append(code)
        if self.exchange_error:
            raise GoogleOAuthError(self.exchange_error)
        return self.tokens

    def revoke(self, token):
        self.revoked.append(token)
        if self.revoke_error:
            raise GoogleOAuthError(self.revoke_error)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/settings/google/callback")
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")
    holder = {"client": FakeClient()}
    monkeypatch.setattr(google_oauth, "get_client", lambda: holder["client"])
    return holder


@pytest.fixture()
def users(make_user):
    return dict(admin=make_user("admin"), staff=make_user("staff"), therapist=make_user("therapist"),
                accountant=make_user("accountant"))


def _connect(client, auth, users, code=CODE):
    """走完整個 OAuth 流程：connect → 取出 state → callback。回傳 callback 的 redirect response。"""
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    assert r.status_code == 200, r.text
    state = parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]
    return client.get("/settings/google/callback", params={"code": code, "state": state}, follow_redirects=False)


def _result(resp) -> str:
    assert resp.status_code == 302, resp.text
    return parse_qs(urlparse(resp.headers["location"]).query)["gcal"][0]


def _row(db):
    db.expire_all()
    return db.execute(text("SELECT status, google_email, refresh_token_enc, scopes FROM google_oauth_connections")).first()


# ---- 設定：預設值與權限 --------------------------------------------------------
def test_defaults_and_readers(client, auth, users, env):
    r = client.get("/settings/clinic", headers=auth(users["admin"]))
    assert r.status_code == 200
    d = r.json()
    assert d["event_title_format"] == "type_room_name"  # 預設 (d)：診所已決定
    assert d["staff_share_emails"] == [] and d["push_therapist_notes_to_google"] is False
    assert d["ical_follow_title_format"] is False
    assert (d["resync_lookback_days"], d["resync_lookahead_days"]) == (30, 180)
    assert d["connection"]["status"] == "disconnected" and d["connection"]["configured"] is True
    assert d["can_edit"] is True
    s = client.get("/settings/clinic", headers=auth(users["staff"])).json()
    assert s["can_edit"] is False
    for who in ("therapist", "accountant"):
        assert client.get("/settings/clinic", headers=auth(users[who])).status_code == 403
    assert client.get("/settings/clinic").status_code in (401, 403)


def test_only_admin_can_change_settings_and_connection(client, auth, users, env):
    for who in ("staff", "therapist", "accountant"):
        h = auth(users[who])
        assert client.patch("/settings/clinic", headers=h, json={"event_title_format": "type_room_code"}).status_code == 403
        assert client.post("/settings/google/connect", headers=h).status_code == 403
        assert client.post("/settings/google/disconnect", headers=h).status_code == 403
    for method, path in (("patch", "/settings/clinic"), ("post", "/settings/google/connect"),
                         ("post", "/settings/google/disconnect")):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_all_four_title_formats_selectable_and_unknown_rejected(client, auth, users, env):
    h = auth(users["admin"])
    for fmt in ("type_room", "type_room_code", "type_room_abbrev", "type_room_name"):
        r = client.patch("/settings/clinic", headers=h, json={"event_title_format": fmt})
        assert r.status_code == 200 and r.json()["event_title_format"] == fmt
    assert client.patch("/settings/clinic", headers=h, json={"event_title_format": "full_name"}).status_code == 422


def test_patch_settings_validates_and_audits(client, auth, users, env, db):
    h = auth(users["admin"])
    r = client.patch("/settings/clinic", headers=h, json={
        "event_title_format": "type_room_abbrev",
        "resync_lookback_days": 7, "push_therapist_notes_to_google": True})
    assert r.status_code == 200
    d = r.json()
    assert d["event_title_format"] == "type_room_abbrev"
    assert d["staff_share_emails"] == []  # 行政名單只能走 PUT /settings/google/staff-emails
    assert d["resync_lookback_days"] == 7 and d["push_therapist_notes_to_google"] is True
    assert d["resync_lookahead_days"] == 180  # 沒送的欄位不變
    # 持久化
    assert client.get("/settings/clinic", headers=h).json()["event_title_format"] == "type_room_abbrev"
    assert db.execute(text("SELECT count(*) FROM clinic_settings")).scalar() == 1
    n = db.execute(text("SELECT count(*) FROM audit_log WHERE table_name = 'clinic_settings'")).scalar()
    assert n == 1


@pytest.mark.parametrize("body", [
    {"event_title_format": "full_name"},
    {"staff_share_emails": ["a@b.com"]},  # 不能從這裡改：改了不會同步各日曆的分享
    {"resync_lookback_days": -1},
    {"resync_lookahead_days": 0},
    {"resync_lookahead_days": 9999},
])
def test_patch_settings_rejects_bad_values(client, auth, users, env, body):
    assert client.patch("/settings/clinic", headers=auth(users["admin"]), json=body).status_code == 422


# ---- connect ------------------------------------------------------------------
def test_connect_returns_google_url_with_required_params(client, auth, users, env):
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    assert r.status_code == 200
    url = urlparse(r.json()["authorization_url"])
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert q["client_id"] == ["test-client-id"]
    assert q["redirect_uri"] == ["http://localhost:8000/settings/google/callback"]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    scopes = q["scope"][0].split()
    for s in CALENDAR_SCOPES:
        assert s in scopes
    assert "https://www.googleapis.com/auth/calendar" not in scopes  # 不採用較寬的 scope
    assert "test-client-secret" not in r.text  # client secret 絕不外流


def test_connect_503_names_the_missing_setting(client, auth, users, monkeypatch):
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    for k in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"):
        monkeypatch.setattr(settings, k, "x")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    assert r.status_code == 503 and "GOOGLE_OAUTH_CLIENT_SECRET" in r.json()["detail"]
    cfg = client.get("/settings/clinic", headers=auth(users["admin"])).json()["connection"]
    assert cfg["configured"] is False and cfg["missing_settings"] == ["GOOGLE_OAUTH_CLIENT_SECRET"]


def test_connect_503_without_fernet_key(client, auth, users, env, monkeypatch):
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", "")
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    assert r.status_code == 503 and "GCAL_TOKEN_FERNET_KEY" in r.json()["detail"]


# ---- callback：成功 ------------------------------------------------------------
def test_callback_success_stores_encrypted_token_and_leaks_nothing(client, auth, users, env, db):
    resp = _connect(client, auth, users)
    assert _result(resp) == "connected"
    loc = resp.headers["location"]
    assert loc.startswith("http://localhost:3000/admin?") and REFRESH not in loc and CODE not in loc
    assert env["client"].codes == [CODE]

    status, email, enc, scopes = _row(db)
    assert status == "active" and email == "clinic@gmail.com"
    assert enc and enc != REFRESH and "REFRESH" not in enc  # 入庫的是密文
    assert secret_box.decrypt(enc) == REFRESH  # 解得回來
    for s in CALENDAR_SCOPES:
        assert s in scopes.split()

    # 任何 API 回應都不含 token 或密文
    d = client.get("/settings/clinic", headers=auth(users["admin"]))
    conn = d.json()["connection"]
    assert conn["status"] == "active" and conn["google_email"] == "clinic@gmail.com"
    assert conn["last_success_at"] and conn["connected_at"]
    assert REFRESH not in d.text and enc not in d.text and "refresh_token" not in d.text
    # staff 也只看得到狀態，沒有密文
    s = client.get("/settings/clinic", headers=auth(users["staff"]))
    assert enc not in s.text and s.json()["connection"]["status"] == "active"
    # 稽核紀錄有記連結動作，但不含 token
    audit = db.execute(text("SELECT string_agg(after_data::text, ' ') FROM audit_log "
                            "WHERE table_name = 'google_oauth_connections'")).scalar()
    assert audit and "clinic@gmail.com" in audit and REFRESH not in audit and enc not in audit
    assert db.execute(text("SELECT operation FROM audit_log WHERE table_name = 'google_oauth_connections'")).scalar() == "CONNECT"


def test_reconnect_replaces_token_single_row(client, auth, users, env, db):
    _connect(client, auth, users)
    first = _row(db)[2]
    env["client"].tokens = TokenResult(refresh_token="1//NEW-REFRESH", scope=ALL_SCOPES, email="clinic@gmail.com")
    assert _result(_connect(client, auth, users)) == "connected"
    assert db.execute(text("SELECT count(*) FROM google_oauth_connections")).scalar() == 1
    assert secret_box.decrypt(_row(db)[2]) == "1//NEW-REFRESH" and _row(db)[2] != first


# ---- callback：失敗都不存東西 ---------------------------------------------------
def test_callback_rejects_bad_state(client, auth, users, env, db):
    for state in (None, "", "garbage", "a.b.c"):
        params = {"code": CODE} | ({"state": state} if state is not None else {})
        r = client.get("/settings/google/callback", params=params, follow_redirects=False)
        assert _result(r) == "invalid_state"
    assert env["client"].codes == []  # 連 Google 都沒呼叫
    assert _row(db) is None


def test_callback_rejects_expired_state(client, users, env, db):
    state = jwt.encode({"purpose": "gcal_oauth", "sub": str(users["admin"].id),
                        "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                       gs._state_key(), algorithm=settings.JWT_ALGORITHM)
    r = client.get("/settings/google/callback", params={"code": CODE, "state": state}, follow_redirects=False)
    assert _result(r) == "invalid_state" and _row(db) is None


def test_callback_rejects_state_for_non_admin_and_wrong_signature(client, auth, users, env, db):
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    staff_state = jwt.encode({"purpose": "gcal_oauth", "sub": str(users["staff"].id), "exp": exp},
                             gs._state_key(), algorithm=settings.JWT_ALGORITHM)
    forged = jwt.encode({"purpose": "gcal_oauth", "sub": str(users["admin"].id), "exp": exp},
                        "some-other-secret", algorithm=settings.JWT_ALGORITHM)
    for st in (staff_state, forged):
        r = client.get("/settings/google/callback", params={"code": CODE, "state": st}, follow_redirects=False)
        assert _result(r) == "invalid_state"
    # 登入用的 access token 不能拿來當 state
    access = auth(users["admin"])["Authorization"].split()[1]
    r = client.get("/settings/google/callback", params={"code": CODE, "state": access}, follow_redirects=False)
    assert _result(r) == "invalid_state"
    assert _row(db) is None


def test_state_token_cannot_be_used_as_login_token(client, auth, users, env):
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    state = parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]
    me = client.get("/settings/clinic", headers={"Authorization": f"Bearer {state}"})
    assert me.status_code == 401  # state 用不同金鑰簽，不能冒充登入


def test_callback_user_denied(client, auth, users, env, db):
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    state = parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]
    resp = client.get("/settings/google/callback", params={"error": "access_denied", "state": state}, follow_redirects=False)
    assert _result(resp) == "denied" and _row(db) is None


def test_callback_exchange_failure(client, auth, users, env, db):
    env["client"] = FakeClient(exchange_error="invalid_grant")
    assert _result(_connect(client, auth, users)) == "token_exchange_failed"
    assert _row(db) is None


def test_callback_missing_scope_stores_nothing_and_keeps_existing(client, auth, users, env, db):
    _connect(client, auth, users)
    before = _row(db)
    partial = TokenResult(refresh_token="1//OTHER", scope=CALENDAR_SCOPES[0] + " openid", email="clinic@gmail.com")
    env["client"] = FakeClient(tokens=partial)
    assert _result(_connect(client, auth, users)) == "missing_scope"
    assert _row(db) == before  # 原本有效的連線沒被動到


def test_callback_without_refresh_token(client, auth, users, env, db):
    env["client"] = FakeClient(tokens=TokenResult(refresh_token=None, scope=ALL_SCOPES, email="clinic@gmail.com"))
    assert _result(_connect(client, auth, users)) == "no_refresh_token"
    assert _row(db) is None


def test_callback_config_error_when_key_disappears(client, auth, users, env, db, monkeypatch):
    r = client.post("/settings/google/connect", headers=auth(users["admin"]))
    state = parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", "")
    resp = client.get("/settings/google/callback", params={"code": CODE, "state": state}, follow_redirects=False)
    assert _result(resp) == "config_error" and _row(db) is None


# ---- disconnect ---------------------------------------------------------------
def test_disconnect_revokes_and_clears_ciphertext(client, auth, users, env, db):
    _connect(client, auth, users)
    r = client.post("/settings/google/disconnect", headers=auth(users["admin"]))
    assert r.status_code == 200 and r.json()["status"] == "disconnected"
    assert env["client"].revoked == [REFRESH]  # 向 Google 撤銷的是解密後的 token
    status, _, enc, _ = _row(db)
    assert status == "disconnected" and enc is None  # 密文已清掉
    assert client.get("/settings/clinic", headers=auth(users["admin"])).json()["connection"]["status"] == "disconnected"
    # 重複解除是冪等的
    assert client.post("/settings/google/disconnect", headers=auth(users["admin"])).status_code == 200
    assert env["client"].revoked == [REFRESH]


def test_disconnect_still_clears_when_revoke_fails(client, auth, users, env, db):
    _connect(client, auth, users)
    env["client"].revoke_error = "invalid_token"
    assert client.post("/settings/google/disconnect", headers=auth(users["admin"])).json()["status"] == "disconnected"
    assert _row(db)[2] is None


def test_disconnect_when_never_connected(client, auth, users, env):
    r = client.post("/settings/google/disconnect", headers=auth(users["admin"]))
    assert r.status_code == 200 and r.json()["status"] == "disconnected"


# ---- log 不含機密 --------------------------------------------------------------
def test_logs_never_contain_secrets(client, auth, users, env, caplog):
    caplog.set_level(logging.DEBUG)
    env["client"] = FakeClient(exchange_error="invalid_grant")
    _connect(client, auth, users)  # 失敗路徑會寫 log
    env["client"] = FakeClient()
    _connect(client, auth, users)
    client.post("/settings/google/disconnect", headers=auth(users["admin"]))
    logs = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (REFRESH, CODE, "test-client-secret"):
        assert secret not in logs
    assert "invalid_grant" in logs  # 只記 Google 的錯誤碼


def test_access_log_filter_redacts_oauth_query():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                            '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:5000", "GET", f"/settings/google/callback?code={CODE}&state=eyJhbGciOi.x.y&scope=a", "1.1", 302),
                            None)
    assert gs._RedactOAuthQuery().filter(rec)
    line = rec.getMessage()
    assert CODE not in line and "eyJhbGciOi" not in line and "[REDACTED]" in line


# ---- 加密 ---------------------------------------------------------------------
def test_secret_box_roundtrip_and_failure_messages(monkeypatch):
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    a, b = secret_box.encrypt(REFRESH), secret_box.encrypt(REFRESH)
    assert a != b and REFRESH not in a  # 每次密文不同、不含明文
    assert secret_box.decrypt(a) == REFRESH
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", Fernet.generate_key().decode())  # 換了金鑰
    with pytest.raises(secret_box.SecretBoxError) as e:
        secret_box.decrypt(a)
    assert REFRESH not in str(e.value) and a not in str(e.value)


@pytest.mark.parametrize("key", ["", "   ", "not-a-valid-key"])
def test_secret_box_requires_valid_key(monkeypatch, key):
    monkeypatch.setattr(settings, "GCAL_TOKEN_FERNET_KEY", key)
    assert secret_box.is_configured() is False
    with pytest.raises(secret_box.SecretBoxError):
        secret_box.encrypt("x")


# ---- Google 用戶端（不連外網）--------------------------------------------------
def test_email_from_id_token():
    import base64

    def tok(claims):
        body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return f"h.{body}.s"

    assert google_oauth._email_from_id_token(tok({"email": "Clinic@Gmail.com", "email_verified": True})) == "clinic@gmail.com"
    assert google_oauth._email_from_id_token(tok({"email": "x@y.z", "email_verified": False})) is None
    assert google_oauth._email_from_id_token("garbage") is None and google_oauth._email_from_id_token(None) is None


def test_exchange_code_error_does_not_leak(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, __import__("io").BytesIO(b'{"error": "invalid_grant"}'))

    monkeypatch.setattr(google_oauth.urllib.request, "urlopen", boom)
    c = GoogleOAuthClient("cid", "SECRET-VALUE", "http://localhost/cb")
    with pytest.raises(GoogleOAuthError) as e:
        c.exchange_code(CODE)
    assert e.value.code == "invalid_grant"
    assert CODE not in str(e.value) and "SECRET-VALUE" not in str(e.value) and e.value.__cause__ is None

    def down(req, timeout=None):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(google_oauth.urllib.request, "urlopen", down)
    with pytest.raises(GoogleOAuthError) as e:
        c.exchange_code(CODE)
    assert e.value.code == "network_error"


def test_get_client_reports_missing_settings(monkeypatch):
    for k in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"):
        monkeypatch.setattr(settings, k, "")
    with pytest.raises(google_oauth.GoogleOAuthNotConfigured) as e:
        google_oauth.get_client()
    assert len(e.value.missing) == 3


# ---- 資料表與 migration -----------------------------------------------------------
def test_tables_are_single_row_and_validated(db):
    db.execute(text("INSERT INTO clinic_settings (id) VALUES (1)"))
    db.commit()
    assert db.execute(text("SELECT event_title_format FROM clinic_settings")).scalar() == "type_room_name"  # 資料庫預設也是 (d)
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO clinic_settings (id) VALUES (2)"))
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE clinic_settings SET event_title_format = 'full_name'"))
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO google_oauth_connections (id, status) VALUES (1, 'weird')"))
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO google_oauth_connections (id) VALUES (2)"))
    db.rollback()


def _mig():
    path = API_DIR / "alembic" / "versions" / "zj0f4a5b6c7d_gcal_and_settings.py"
    spec = importlib.util.spec_from_file_location("zj0f4a5b6c7d", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(_mig(), fn)()


def _tables():
    return set(inspect(engine).get_table_names())


def _restore_head_title_constraint():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location("zm3c7d8e9f0a", API_DIR / "alembic" / "versions" / "zm3c7d8e9f0a_gcal_title_name.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()
    # zj 重建的 clinic_settings 也沒有後續 migration 加的欄位（失約費設定），一併補上
    spec = importlib.util.spec_from_file_location("zp6f0a1b2c3d", API_DIR / "alembic" / "versions" / "zp6f0a1b2c3d_no_show_fee_settings.py")
    mod2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod2)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod2.upgrade()


def test_migration_roundtrip_touches_only_its_own_tables(db, make_user):
    make_user("admin")  # 既有資料不能被動到
    mine = {"clinic_settings", "google_oauth_connections"}
    assert mine <= _tables()
    before = _tables() - mine
    db.rollback()
    try:
        _run("downgrade")
        assert not (mine & _tables()) and before == _tables()  # 只拿掉自己的兩張表
        assert db.execute(text("SELECT count(*) FROM users")).scalar() == 1
        db.rollback()
        _run("upgrade")
        assert mine <= _tables() and before == _tables() - mine
        assert db.execute(text("SELECT count(*) FROM clinic_settings")).scalar() == 0  # 預設列由程式第一次讀取時建立
    finally:
        db.rollback()
        if not mine <= _tables():
            _run("upgrade")
        _restore_head_title_constraint()  # zj 重建的表帶的是舊的三選一 constraint，補上後續 migration（標題格式 d）


def test_migration_chain_and_only_adds():
    txt = (API_DIR / "alembic" / "versions" / "zj0f4a5b6c7d_gcal_and_settings.py").read_text(encoding="utf-8")
    assert 'down_revision = "zi9e3f4a5b6e"' in txt
    children = [p.name for p in (API_DIR / "alembic" / "versions").glob("*.py")
                if 'down_revision = "zj0f4a5b6c7d"' in p.read_text(encoding="utf-8")]
    assert set(children) <= {"zk1a5b6c7d8e_gcal_calendars.py"}  # 後面只能接 PR B 的 migration（鏈不分叉）
    assert txt.count("drop_table") == 2 and "op.execute" not in txt and "DELETE" not in txt.upper()
