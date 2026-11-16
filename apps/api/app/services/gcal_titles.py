"""Google 事件的標題與內容（docs/gcal-sync-plan.md §5）。全部是純函式，不碰資料庫與網路。

隱私規則（測試鎖死）。診所決定的事件內容：
- 標題：類型 · 診間，依設定再加 個案代號 (b)／姓名縮寫 (c)／個案全名 (d，預設)；有金額時標題結尾加「 · $金額」。
  只有 (d) 會輸出個案全名；(a)(b)(c) 絕不輸出完整姓名。
- 描述：固定說明、「給心理師的提醒」（類型、診間、是否初診；機構案再加方案名稱與自負額），
  以及備註分段（「備註給心理師」接在 `note_sections` 之後，分段標示）。總額只放標題，描述不放。
- 永遠不放：電話、Email、地址、主訴／病歷／治療備註、帳務備註、機構名稱、其他心理師、任何 token。
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

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


def format_amount(amount) -> str | None:
    """金額文字，例如 $1,500；沒有金額（None 或 0 以下）回 None，呼叫端就不顯示。"""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        return None
    if value <= 0:
        return None
    return f"${value:,.0f}" if value == value.to_integral_value() else f"${value:,.2f}"


def amount_suffix(a: Appointment) -> str | None:
    """標題結尾的金額文字。自費：「$全額」；機構：「$總額（自付 $X）」，
    全額補助「$總額（機構全額）」，自付額未設定「$總額（自付未設定）」。總額為 0 或沒有就不顯示。"""
    total = format_amount(a.amount)
    if total is None:
        return None
    if (a.funding_source or "self_pay") != "institution":
        return total
    if a.self_pay_amount is None:
        return f"{total}（自付未設定）"
    own = format_amount(a.self_pay_amount)
    if own is None:  # 自付 0 ＝ 機構全額補助
        return f"{total}（機構全額）"
    return f"{total}（自付 {own}）"


def event_title(a: Appointment, title_format: str) -> str:
    """(a) type_room：「諮商 · 2B」；(b) type_room_code：再加個案代號；(c) type_room_abbrev：再加姓名縮寫；
    (d) type_room_name：再加個案全名（預設）。(a)(b)(c) 缺資料時退化成前一種，絕不改塞姓名。
    總額大於 0 時，結尾加金額：自費「 · $1,500」；機構「 · $1,600（自付 $200）」（見 amount_suffix）。"""
    kind, place = _kind_and_place(a)
    parts = [kind] + ([place] if place else [])
    case = a.couple_case or a.case
    if title_format == "type_room_code" and case is not None and (case.case_code or "").strip():
        parts.append(case.case_code.strip())
    elif title_format == "type_room_abbrev" and case is not None:
        abbr = abbreviate_name(case.name)
        if abbr:
            parts.append(abbr)
    elif title_format == "type_room_name" and case is not None and (case.name or "").strip():
        parts.append(" ".join(case.name.split()))
    amount = amount_suffix(a)
    if amount:
        parts.append(amount)
    return SEP.join(parts)


SESSION_LABEL = {"in_person": "現場", "online": "視訊", "outdoor": "外展"}


def self_pay_text(value) -> str:
    """自負額：NULL＝未設定；0＝0（全額補助）；其餘「200 元」。描述不用 $ 符號（$ 只出現在標題）。"""
    if value is None:
        return "未設定"
    try:
        v = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return "未設定"
    if v == 0:
        return "0（全額補助）"
    return f"{v:,.0f} 元" if v == v.to_integral_value() else f"{v:,.2f} 元"


def reminder_lines(a: Appointment, plan_name: str | None = None) -> list[str]:
    """給心理師看的提醒。只有類型、診間、是否初診、方案名稱、自負額；不含任何個案識別或聯絡資料。"""
    lines = [f"類型：{SESSION_LABEL.get(a.session_type, a.session_type)}"]
    if a.session_type == "in_person":
        lines.append(f"診間：{a.room.room_code if a.room is not None else '未指定'}")
    lines.append(f"初診：{'是' if a.is_intake else '否'}")
    if (a.funding_source or "self_pay") == "institution":
        lines.append(f"方案：{(plan_name or '').strip() or '未設定'}")
        lines.append(f"自負額：{self_pay_text(a.self_pay_amount)}")
    return lines


def event_description(a: Appointment, note_sections: list[tuple[str, str]] | None = None,
                      plan_name: str | None = None) -> str:
    """固定說明＋給心理師的提醒；備註分段標示（標題、內文），空內文不輸出。總額不放描述（只在標題）。
    note_sections 由呼叫端依來源提供，例如 [("預約備註", ...), ("備註給心理師", ...)]。"""
    lines = [DESCRIPTION, "\n【給心理師的提醒】", *reminder_lines(a, plan_name)]
    for heading, body in note_sections or []:
        body = (body or "").strip()
        if body:
            lines.append(f"\n【{heading}】\n{body}")
    return "\n".join(lines)


def event_id(appointment_id: int) -> str:
    """由預約 id 決定的事件 id（Google 只允許 a-v、0-9，長度 5–1024）：重複推送不會產生重複事件。"""
    return f"cheer{appointment_id:07d}"


def event_body(a: Appointment, title_format: str, note_sections: list[tuple[str, str]] | None = None,
               plan_name: str | None = None) -> dict:
    lo, up = a.time_range.lower, a.time_range.upper
    return {
        "id": event_id(a.id),
        "summary": event_title(a, title_format),
        "description": event_description(a, note_sections, plan_name),
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
