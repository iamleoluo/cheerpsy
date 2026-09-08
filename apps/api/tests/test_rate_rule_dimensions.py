"""費率規則的維度守門（07 §6.2）。

背景：pricing.rule_matches() 對「不認得的條件鍵」是**寬容跳過**而不是判定
失敗（pricing.py:67-68，為了避免一個打字錯誤癱瘓整個報價）。這個設計的代價
是：規則寫錯 key 不會噴錯，只會靜默地變成「命中全部」——價錢就錯了，而且
從畫面上看不出來。

所以必須有一支測試把「所有 when_json 的 key 都在 field_map 裡」變成紅燈。
這也是為什麼 field_map 與 seed 改寫要在同一個 commit：先寫規則後補 key，
中間那段時間所有規則都是 catch-all。

另外驗諮商型態（consult_type）這個新維度真的接通了——南家扶／家防中心／
國軍原本都因為維度撞名而永遠報價 $0。
"""

import json

from decimal import Decimal

import pytest

import app.models  # noqa: F401 — 註冊全部 mapper，否則 relationship 解析不到 Institution
from app.institution.models.rate_rule import InstRateRule
from app.institution.rules.pricing import RateRuleContext, resolve_rate, rule_matches

# 與 pricing.rule_matches() 的 field_map 對齊。新增維度時兩邊要一起改，
# 這份清單就是那道提醒。
KNOWN_KEYS = {"session_type", "consult_type", "visit_seq", "duration_min",
              "location_kind", "time_band", "sub_unit"}


class TestFieldMapCoverage:
    def test_every_seeded_rule_key_is_known(self, db):
        """跑過 seed 的資料庫裡，不可以有任何一條規則用了 field_map 不認得的 key。"""
        unknown = []
        for r in db.query(InstRateRule).all():
            for key in json.loads(r.when_json or "{}").keys():
                if key not in KNOWN_KEYS:
                    unknown.append((r.id, r.label, key))
        assert not unknown, f"這些規則的條件鍵不在 field_map 裡，會靜默變成命中全部：{unknown}"

    def test_unknown_key_would_match_everything(self):
        """把那個危險行為釘住，免得有人以為未知 key 是安全的。"""
        assert rule_matches({"typo_key": "whatever"}, RateRuleContext(session_type="in_person"))


class TestConsultTypeDimension:
    """consult_type 與 session_type 是不同軸——三種諮商型態都可以是「現場」。"""

    RULES = [
        {"id": 1, "sort_order": 1, "when_json": '{"consult_type": "individual"}', "unit_price": 2000, "case_payable": 0},
        {"id": 2, "sort_order": 2, "when_json": '{"consult_type": "parenting"}', "unit_price": 1000, "case_payable": 0},
        {"id": 3, "sort_order": 3, "when_json": '{"consult_type": "family"}', "unit_price": 2400, "case_payable": 0},
        {"id": 4, "sort_order": 99, "when_json": "{}", "unit_price": 2000, "case_payable": 0},
    ]

    @pytest.mark.parametrize("consult_type,expected", [
        ("individual", 2000), ("parenting", 1000), ("family", 2400),
    ])
    def test_prices_differ_by_consult_type_at_the_same_session_type(self, consult_type, expected):
        ctx = RateRuleContext(session_type="in_person", consult_type=consult_type)
        matched = resolve_rate(self.RULES, ctx)
        assert matched is not None
        assert matched.unit_price == Decimal(str(expected))

    def test_falls_back_to_catch_all(self):
        matched = resolve_rate(self.RULES, RateRuleContext(session_type="online", consult_type="group"))
        assert matched is not None and matched.unit_price == Decimal("2000")

    def test_location_kind_is_matchable(self):
        """QuoteRequest 早就有 location_kind，但建立預約時硬寫 clinic，
        所以 {"location_kind": "home"} 這類規則一直是死的。"""
        rules = [
            {"id": 1, "sort_order": 1, "when_json": '{"location_kind": "home"}', "unit_price": 2500, "case_payable": 0},
            {"id": 2, "sort_order": 99, "when_json": "{}", "unit_price": 1600, "case_payable": 0},
        ]
        home = resolve_rate(rules, RateRuleContext(location_kind="home"))
        clinic = resolve_rate(rules, RateRuleContext(location_kind="clinic"))
        assert home.unit_price == Decimal("2500")
        assert clinic.unit_price == Decimal("1600")


class TestSeededPlansQuoteNonZero:
    """南家扶／家防中心／國軍原本因為維度撞名，任何預約都報 $0。

    刻意在測試自己的交易裡重跑一次 seed_plans()，而不是讀資料庫現有的列
    ——否則測的是「上次誰跑過 seed」的殘留狀態，改了程式碼也不會變紅。
    """

    def _seeded_plans(self, db):
        from app.institution.seed_plans import seed_plans
        # force=True 先清掉資料庫裡的殘留方案再重建，確保測到的是「現在程式碼
        # 寫的規則」，不是上次誰跑過 seed 留下的舊列。db 傳進去 → 不 commit、
        # 不 close，整段跟著測試一起 rollback。
        seed_plans(db=db, force=True)
        return db

    def test_every_seeded_plan_quotes_non_zero(self, db):
        from app.institution.models.plan import InstPlan

        self._seeded_plans(db)
        plans = db.query(InstPlan).all()
        assert plans, "seed_plans() 沒有建立任何方案"

        zero_priced = []
        for plan in plans:
            rules = [
                {"id": r.id, "sort_order": r.sort_order, "when_json": r.when_json,
                 "unit_price": r.unit_price, "case_payable": r.case_payable,
                 "price_source": r.price_source, "label": r.label}
                for r in sorted(plan.rate_rules, key=lambda x: x.sort_order)
            ]
            matched = resolve_rate(rules, RateRuleContext(
                session_type="in_person", consult_type="individual",
                visit_seq=1, duration_min=60, location_kind="clinic",
            ))
            if matched is None:
                zero_priced.append((plan.name, "沒有規則命中 → fallback $0"))
            elif matched.price_source == "fixed" and not (matched.unit_price and matched.unit_price > 0):
                # 鉅微借場地刻意允許 $0（可手動改），其餘方案報 0 就是壞了
                if "借場地" not in plan.name:
                    zero_priced.append((plan.name, f"unit_price={matched.unit_price}"))
        assert not zero_priced, f"這些方案報價為 0：{zero_priced}"

    @pytest.mark.parametrize("plan_name,consult_type,expected", [
        ("南家扶", "individual", 2000),
        ("南家扶", "parenting", 1000),
        ("南家扶", "family", 2400),
        ("家防中心", "individual", 1400),
        ("家防中心", "family", 2000),
    ])
    def test_consult_type_tiers_resolve(self, db, plan_name, consult_type, expected):
        from app.institution.models.plan import InstPlan

        self._seeded_plans(db)
        plan = db.query(InstPlan).filter(InstPlan.name == plan_name).first()
        rules = [
            {"id": r.id, "sort_order": r.sort_order, "when_json": r.when_json,
             "unit_price": r.unit_price, "case_payable": r.case_payable,
             "price_source": r.price_source, "label": r.label}
            for r in sorted(plan.rate_rules, key=lambda x: x.sort_order)
        ]
        matched = resolve_rate(rules, RateRuleContext(
            session_type="in_person", consult_type=consult_type, visit_seq=1,
            duration_min=60, location_kind="clinic",
        ))
        assert matched.unit_price == Decimal(str(expected))
