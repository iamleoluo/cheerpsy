"""費率規則比對引擎。有序、先匹配先贏。見 07 §6.2、§6.3（54 個方案逐一驗算）。

`when` 支援七個變數，每個可以是「精確值」或 {"gte": n} / {"lte": n} 這種簡單
比較。空字典 {} 代表「其餘情況」，通常放在 sort_order 最大的位置當預設值。

這支只負責「哪一條規則命中」，不負責讀資料庫——呼叫端（adapter.py）組好
context 字典後傳進來，方便單元測試不用碰 DB。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class RateRuleContext:
    # session_type = 型式（現場/線上/外展），沿用主系統既有枚舉
    session_type: str | None = None
    # consult_type = 諮商型態（個別/伴侶/家族/親職/團體/講座/會議），07 §6.2 的計價維度。
    # 這兩件事名字很像但是不同軸：家防中心的 個別$2000 / 親職$1000 / 家族$2400
    # 三者都是「現場」，塞不進 session_type。
    consult_type: str | None = None
    visit_seq: int | None = None
    duration_min: int | None = None
    location_kind: str | None = None
    time_band: str | None = None
    sub_unit: str | None = None


@dataclass
class MatchedRule:
    unit_price: Decimal | None
    case_payable: Decimal
    price_source: str  # fixed | therapist_rate
    label: str | None
    resolved_by: str


def _cmp(value: Any, cond: Any) -> bool:
    """比對單一條件。cond 可以是純值，或 {"gte": n}/{"lte": n}/{"gt": n}/{"lt": n}。"""
    if value is None:
        return False
    if isinstance(cond, dict):
        if "gte" in cond and not (value >= cond["gte"]):
            return False
        if "lte" in cond and not (value <= cond["lte"]):
            return False
        if "gt" in cond and not (value > cond["gt"]):
            return False
        if "lt" in cond and not (value < cond["lt"]):
            return False
        return True
    return value == cond


def _context_fields(ctx: RateRuleContext) -> dict[str, Any]:
    return {
        "session_type": ctx.session_type,
        "consult_type": ctx.consult_type,
        "visit_seq": ctx.visit_seq,
        "duration_min": ctx.duration_min,
        "location_kind": ctx.location_kind,
        "time_band": ctx.time_band,
        "sub_unit": ctx.sub_unit,
    }


#: 條件字典允許出現的 key。**寫入端必須拿這個驗**（見 rule_matches 的警告）。
CONDITION_KEYS: frozenset[str] = frozenset(_context_fields(RateRuleContext()))


def unknown_condition_keys(when: dict) -> list[str]:
    """條件字典裡不認得的 key。空清單代表這條規則的條件都看得懂。"""
    return sorted(k for k in (when or {}) if k not in CONDITION_KEYS)


def rule_matches(when: dict, ctx: RateRuleContext) -> bool:
    """空字典永遠命中（預設規則）。其餘每個 key 都要通過才算命中。

    ⚠️ 不認得的 key 會被**跳過**而不是判失敗。這是刻意的：報價是線上流程，
    一個打錯字的條件鍵不應該讓整個方案報不出價。但代價很陡——
    `{"sesion_type": "online"}`（少一個 s）會變成一條**命中全部**的規則，
    而且悄悄地，只有在有人核對帳目時才會發現金額不對。

    所以「寬容」只能存在於讀取端。任何寫入費率規則的路徑都必須先用
    `unknown_condition_keys()` 擋下來，讓打錯字在存檔當下就變成紅字。
    """
    if not when:
        return True
    field_map = _context_fields(ctx)
    for key, cond in when.items():
        if key not in field_map:
            continue  # 理由見 docstring：寬容只在讀取端，寫入端必須擋
        if not _cmp(field_map[key], cond):
            return False
    return True


def resolve_rate(rules: list[dict], ctx: RateRuleContext) -> MatchedRule | None:
    """rules 需已依 sort_order 排序。回傳第一條命中的規則，找不到回傳 None。

    每個 rule dict 形狀：
        {"id": 7, "sort_order": 2, "when_json": '{"visit_seq": 2}',
         "price_source": "fixed", "unit_price": 1400, "case_payable": 200, "label": "..."}
    """
    for rule in rules:
        when = json.loads(rule.get("when_json") or "{}")
        if rule_matches(when, ctx):
            unit_price = rule.get("unit_price")
            return MatchedRule(
                unit_price=Decimal(str(unit_price)) if unit_price is not None else None,
                case_payable=Decimal(str(rule.get("case_payable") or 0)),
                price_source=rule.get("price_source", "fixed"),
                label=rule.get("label"),
                resolved_by=f"rate_rule#{rule.get('id')} ({when or 'default'})",
            )
    return None
