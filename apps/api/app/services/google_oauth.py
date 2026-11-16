"""Google OAuth 用戶端（只做授權碼換 token、撤銷）。刻意不用 google-auth 套件，只用標準庫 urllib。

測試一律不連外網：router 透過 get_client() 取得用戶端，測試以 monkeypatch 換成 fake。
錯誤與 log 絕不包含 authorization code、access／refresh token。
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# 計畫書 §1.2：建次要日曆並寫事件 + 設定分享。沙盒（2026-11-16）實測這組合足夠，不需要較寬的 calendar。
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.app.created",
    "https://www.googleapis.com/auth/calendar.acls",
)
# 只為了在授權完成時讀回「是哪個 Google 帳號」（id_token 的 email）；不屬敏感 scope，不涉及日曆資料。
IDENTITY_SCOPES = ("openid", "email")
REQUESTED_SCOPES = CALENDAR_SCOPES + IDENTITY_SCOPES

HTTP_TIMEOUT_SECONDS = 15


class GoogleOAuthError(Exception):
    """與 Google 溝通失敗。code 是 Google 回的錯誤碼（如 invalid_grant）或本地分類；訊息不含任何機密。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GoogleOAuthNotConfigured(Exception):
    def __init__(self, missing: list[str]):
        super().__init__("缺少環境變數：" + "、".join(missing))
        self.missing = missing


@dataclass
class TokenResult:
    refresh_token: str | None
    scope: str  # Google 實際授予的 scope（空白分隔）
    email: str | None


def missing_settings() -> list[str]:
    need = {
        "GOOGLE_OAUTH_CLIENT_ID": settings.GOOGLE_OAUTH_CLIENT_ID,
        "GOOGLE_OAUTH_CLIENT_SECRET": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "GOOGLE_OAUTH_REDIRECT_URI": settings.GOOGLE_OAUTH_REDIRECT_URI,
    }
    return [k for k, v in need.items() if not (v or "").strip()]


def _email_from_id_token(id_token: str | None) -> str | None:
    """id_token 是直接從 Google token endpoint（TLS）拿到的，這裡只讀 email，不拿來做授權判斷。"""
    if not id_token:
        return None
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        email = claims.get("email")
        return email.lower() if isinstance(email, str) and claims.get("email_verified", True) else None
    except Exception:
        return None


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(REQUESTED_SCOPES),
            "access_type": "offline",  # 要 refresh token
            "prompt": "consent",  # 每次都出同意畫面，確保 Google 會再給 refresh token
            "include_granted_scopes": "false",
            "state": state,
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _post(self, url: str, data: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            try:
                code = json.loads(e.read()).get("error", "http_error")
            except Exception:
                code = "http_error"
            raise GoogleOAuthError(str(code)[:100]) from None  # 不附帶原始例外（可能含請求內容）
        except (urllib.error.URLError, TimeoutError, OSError):
            raise GoogleOAuthError("network_error") from None
        try:
            return json.loads(body or b"{}")
        except json.JSONDecodeError:
            raise GoogleOAuthError("bad_response") from None

    def exchange_code(self, code: str) -> TokenResult:
        data = self._post(TOKEN_URL, {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        })
        return TokenResult(
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope", ""),
            email=_email_from_id_token(data.get("id_token")),
        )

    def revoke(self, token: str) -> None:
        self._post(REVOKE_URL, {"token": token})


def get_client() -> GoogleOAuthClient:
    missing = missing_settings()
    if missing:
        raise GoogleOAuthNotConfigured(missing)
    return GoogleOAuthClient(
        settings.GOOGLE_OAUTH_CLIENT_ID, settings.GOOGLE_OAUTH_CLIENT_SECRET, settings.GOOGLE_OAUTH_REDIRECT_URI
    )
