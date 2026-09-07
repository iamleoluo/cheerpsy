"""費率規則比對引擎。有序、先匹配先贏。見 07 §6.2、§6.3（54 個方案逐一驗算）。

`when` 支援六個變數，每個可以是「精確值」或 {"gte": n} / {"lte": n} 這種簡單
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
    session_type: str | None = None
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


def rule_matches(when: dict, ctx: RateRuleContext) -> bool:
    """空字典永遠命中（預設規則）。其餘每個 key 都要通過才算命中。"""
    if not when:
        return True
    field_map = {
        "session_type": ctx.session_type,
        "visit_seq": ctx.visit_seq,
        "duration_min": ctx.duration_min,
        "location_kind": ctx.location_kind,
        "time_band": ctx.time_band,
        "sub_unit": ctx.sub_unit,
    }
    for key, cond in when.items():
        if key not in field_map:
            continue  # 未知條件鍵，寬容跳過而非直接判失敗，避免資料打字錯誤癱瘓報價
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
