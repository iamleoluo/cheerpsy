"""Google 事件的標題與內容（docs/gcal-sync-plan.md §5）。全部是純函式，不碰資料庫與網路。

隱私硬規則（測試鎖死）：事件只會有 類型／診間／（個案代號）／（姓名縮寫）、時間、一句固定說明，
以及預約的內部編號。絕不含完整姓名、電話、Email、地址、病歷、金額、備註本文。
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from app.models.appointment import Appointment

TAIPEI = timezone(timedelta(hours=8))  # 台灣沒有日光節約時間，固定偏移即可，不依賴 tzdata
TIME_ZONE = "Asia/Taipei"
DESCRIPTION = "由 Cheerpsy 同步，請勿在此修改。"
SEP = " · "

COMPOUND_SURNAMES = ("歐陽", "司馬", "諸葛", "上官", "夏侯", "皇甫", "尉遲", "公孫", "慕容", "令狐", "長孫", "宇文")
_CJK = re.compile(r"^[㐀-䶿一-鿿]+$")


def abbreviate_name(name: str | None) -> str | None:
    """姓名縮寫。保證結果「不等於」完整姓名；無法安全縮寫就回 None（呼叫端退化成不含縮寫的標題）。

    中文：兩字名只顯示姓（王明→王）；三字名取前兩字（陳小美→陳小）；複姓取三字（歐陽小明→歐陽小）；
    複姓的三字名（歐陽明）取三字會等於全名，所以只顯示複姓（歐陽）；四字以上的非複姓名視為無法拆解。
    非中文：`Mei Chen` → `Mei C.`；只有一個字回 None。混合文字回 None。"""
    n = " ".join((name or "").split())
    if not n:
        return None
    if _CJK.match(n):
        compound = n[:2] in COMPOUND_SURNAMES
        if compound:
            out = n[:3] if len(n) >= 4 else n[:2]
        elif len(n) == 2:
            out = n[:1]
        elif len(n) == 3:
            out = n[:2]
        else:
            return None
        return out if 0 < len(out) < len(n) else None
    if " " in n and all(re.match(r"^[A-Za-z][A-Za-z'\-.]*$", t) for t in n.split(" ")):
        parts = n.split(" ")
        out = f"{parts[0]} {parts[-1][0].upper()}."
        return out if out != n else None
    return None


def _kind_and_place(a: Appointment) -> tuple[str, str | None]:
    if a.session_type == "outdoor":
        return "外展", None
    kind = "初診" if a.is_intake else "諮商"
    if a.session_type == "online":
        return kind, "線上"
    return kind, (a.room.room_code if a.room is not None else None)


def event_title(a: Appointment, title_format: str) -> str:
    """(a) type_room：「諮商 · 2B」；(b) type_room_code：再加個案代號；(c) type_room_abbrev：再加姓名縮寫。
    缺資料時退化成前一種，絕不改塞姓名。"""
    kind, place = _kind_and_place(a)
    parts = [kind] + ([place] if place else [])
    case = a.couple_case or a.case
    if title_format == "type_room_code" and case is not None and (case.case_code or "").strip():
        parts.append(case.case_code.strip())
    elif title_format == "type_room_abbrev" and case is not None:
        abbr = abbreviate_name(case.name)
        if abbr:
            parts.append(abbr)
    return SEP.join(parts)


def event_id(appointment_id: int) -> str:
    """由預約 id 決定的事件 id（Google 只允許 a-v、0-9，長度 5–1024）：重複推送不會產生重複事件。"""
    return f"cheer{appointment_id:07d}"


def event_body(a: Appointment, title_format: str) -> dict:
    lo, up = a.time_range.lower, a.time_range.upper
    return {
        "id": event_id(a.id),
        "summary": event_title(a, title_format),
        "description": DESCRIPTION,
        "start": {"dateTime": _iso(lo), "timeZone": TIME_ZONE},
        "end": {"dateTime": _iso(up), "timeZone": TIME_ZONE},
        "status": "confirmed",
        "extendedProperties": {"private": {"cheerpsyAppointmentId": str(a.id)}},
    }


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TAIPEI).isoformat()


def payload_hash(calendar_id: str, body: dict) -> str:
    raw = json.dumps({"calendar": calendar_id, "body": body}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
