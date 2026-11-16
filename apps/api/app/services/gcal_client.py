"""Google Calendar API 用戶端（PR B 只用到：建日曆、改日曆名稱、ACL 列出／新增／改權限／刪除）。

- 介面 `CalendarClient` 是 Protocol：正式環境用 `GoogleCalendarClient`（標準庫 urllib，不加新套件），
  測試注入 fake，所以測試不連外網。
- `get_calendar_client(db)` 讀出加密的 refresh token → 換 access token。授權失效（invalid_grant）時
  把連線標成 token_invalid 並丟 `GcalNotConnected`。
- 錯誤訊息只含 HTTP 狀態與 Google 的 reason 代碼，絕不含 token、請求內容或 email。
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.gcal import GoogleOAuthConnection
from app.services import google_oauth, secret_box

API_BASE = "https://www.googleapis.com/calendar/v3"
TIME_ZONE = "Asia/Taipei"
CALENDAR_DESCRIPTION = "由 Cheerpsy 同步，請勿在此修改。"
HTTP_TIMEOUT_SECONDS = 20


class GcalNotConnected(Exception):
    """還沒連結 Google、授權已失效，或伺服器缺設定。訊息可直接顯示給使用者。"""

    def __init__(self, message: str, token_invalid: bool = False, transient: bool = False):
        super().__init__(message)
        self.message = message
        self.token_invalid = token_invalid
        self.transient = transient  # 暫時性問題（例如 Google 一時連不上）：不要把工作標成 blocked，稍後再試


class CalendarApiError(Exception):
    """Google Calendar API 回了錯誤。status 是 HTTP 狀態（網路問題為 0）；reason 是 Google 的 reason 代碼。"""

    def __init__(self, status: int, reason: str = ""):
        super().__init__(f"HTTP {status} {reason}".strip())
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class CalendarInfo:
    id: str
    summary: str


@dataclass(frozen=True)
class AclRule:
    rule_id: str
    role: str  # owner / writer / reader / freeBusyReader
    scope_type: str  # user / group / domain / default
    value: str  # email（小寫）；default 類型為空字串


class CalendarClient(Protocol):
    def create_calendar(self, summary: str, time_zone: str, description: str) -> CalendarInfo: ...
    def rename_calendar(self, calendar_id: str, summary: str) -> None: ...
    def list_acl(self, calendar_id: str) -> list[AclRule]: ...
    def insert_acl(self, calendar_id: str, email: str, role: str, send_notifications: bool) -> AclRule: ...
    def patch_acl_role(self, calendar_id: str, rule_id: str, role: str) -> None: ...
    def delete_acl(self, calendar_id: str, rule_id: str) -> None: ...
    def insert_event(self, calendar_id: str, body: dict) -> None: ...  # body 含自訂 id
    def update_event(self, calendar_id: str, event_id: str, body: dict) -> None: ...
    def delete_event(self, calendar_id: str, event_id: str) -> None: ...


def _q(part: str) -> str:
    return urllib.parse.quote(part, safe="")  # calendar id、ruleId 都含 @ 或 :


class GoogleCalendarClient:
    def __init__(self, access_token: str):
        self._token = access_token

    def _request(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None):
        url = f"{API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        })
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            reason = ""
            try:
                errors = json.loads(e.read()).get("error", {}).get("errors", [])
                reason = str(errors[0].get("reason", ""))[:100] if errors else ""
            except Exception:
                pass
            raise CalendarApiError(e.code, reason) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CalendarApiError(0, "network_error") from None
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raise CalendarApiError(0, "bad_response") from None

    @staticmethod
    def _rule(item: dict) -> AclRule:
        scope = item.get("scope") or {}
        return AclRule(
            rule_id=item["id"],
            role=item.get("role", ""),
            scope_type=scope.get("type", ""),
            value=(scope.get("value") or "").lower(),
        )

    def create_calendar(self, summary: str, time_zone: str, description: str) -> CalendarInfo:
        r = self._request("POST", "/calendars", body={"summary": summary, "timeZone": time_zone, "description": description})
        return CalendarInfo(id=r["id"], summary=r.get("summary", summary))

    def rename_calendar(self, calendar_id: str, summary: str) -> None:
        self._request("PATCH", f"/calendars/{_q(calendar_id)}", body={"summary": summary})

    def list_acl(self, calendar_id: str) -> list[AclRule]:
        rules: list[AclRule] = []
        page = None
        while True:
            r = self._request("GET", f"/calendars/{_q(calendar_id)}/acl", params={"pageToken": page} if page else None)
            rules += [self._rule(i) for i in r.get("items", [])]
            page = r.get("nextPageToken")
            if not page:
                return rules

    def insert_acl(self, calendar_id: str, email: str, role: str, send_notifications: bool) -> AclRule:
        r = self._request("POST", f"/calendars/{_q(calendar_id)}/acl",
                          params={"sendNotifications": "true" if send_notifications else "false"},
                          body={"role": role, "scope": {"type": "user", "value": email}})
        return self._rule(r)

    def patch_acl_role(self, calendar_id: str, rule_id: str, role: str) -> None:
        self._request("PATCH", f"/calendars/{_q(calendar_id)}/acl/{_q(rule_id)}",
                      params={"sendNotifications": "false"}, body={"role": role})

    def delete_acl(self, calendar_id: str, rule_id: str) -> None:
        self._request("DELETE", f"/calendars/{_q(calendar_id)}/acl/{_q(rule_id)}")

    # 事件：不寄任何通知（sendUpdates=none）；事件沒有邀請對象
    def insert_event(self, calendar_id: str, body: dict) -> None:
        self._request("POST", f"/calendars/{_q(calendar_id)}/events", params={"sendUpdates": "none"}, body=body)

    def update_event(self, calendar_id: str, event_id: str, body: dict) -> None:
        self._request("PUT", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}",
                      params={"sendUpdates": "none"}, body=body)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._request("DELETE", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}", params={"sendUpdates": "none"})


def get_calendar_client(db: Session) -> CalendarClient:
    """回傳可用的 Calendar 用戶端；沒連結／授權失效／缺設定都丟 GcalNotConnected（訊息可直接給使用者看）。"""
    conn = db.get(GoogleOAuthConnection, 1)
    if conn is None or conn.status == "disconnected" or not conn.refresh_token_enc:
        raise GcalNotConnected("尚未連結 Google 帳號，請管理員先到「系統管理 → 日曆同步」連結")
    if conn.status == "token_invalid":
        raise GcalNotConnected("Google 授權已失效，請管理員重新連結", token_invalid=True)
    if not set(google_oauth.CALENDAR_SCOPES) <= set((conn.scopes or "").split()):
        raise GcalNotConnected("目前的 Google 授權缺少日曆權限，請管理員重新連結", token_invalid=True)
    try:
        refresh_token = secret_box.decrypt(conn.refresh_token_enc)
        access_token = google_oauth.get_client().refresh_access_token(refresh_token)
    except secret_box.SecretBoxError as e:
        raise GcalNotConnected(str(e), token_invalid=True) from None
    except google_oauth.GoogleOAuthNotConfigured as e:
        raise GcalNotConnected("伺服器缺少 Google 設定：" + "、".join(e.missing)) from None
    except google_oauth.GoogleOAuthError as e:
        if e.code == "invalid_grant":
            mark_token_invalid(db, "invalid_grant", "Google 授權已被撤銷或過期，請重新連結")
            raise GcalNotConnected("Google 授權已失效，請管理員重新連結", token_invalid=True) from None
        raise GcalNotConnected("暫時無法向 Google 取得授權，請稍後再試", transient=True) from None
    return GoogleCalendarClient(access_token)


def mark_token_invalid(db: Session, code: str, message: str) -> None:
    conn = db.get(GoogleOAuthConnection, 1)
    if conn is None:
        return
    conn.status = "token_invalid"
    conn.token_invalid_at = datetime.now(timezone.utc)
    conn.last_error_code = code
    conn.last_error_message = message
    db.commit()


def mark_success(db: Session) -> None:
    conn = db.get(GoogleOAuthConnection, 1)
    if conn is not None:
        conn.last_success_at = datetime.now(timezone.utc)
        conn.last_error_code = None
        conn.last_error_message = None
