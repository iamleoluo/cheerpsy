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

from fastapi.testclient import TestClient

import app.models  # noqa: F401 — 註冊全部 mapper，否則 relationship 解析不到 Institution
from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.models.rate_rule import InstRateRule
from app.main import app as fastapi_app
from app.models.user import User
from app.institution.rules.pricing import (
    CONDITION_KEYS,
    RateRuleContext,
    resolve_rate,
    rule_matches,
    unknown_condition_keys,
)

# 直接用 pricing 匯出的那一份，不再在這裡手抄一遍——手抄的版本會跟著漂移，
# 而這支測試的全部價值就在於它跟得上真正的 field_map。
KNOWN_KEYS = CONDITION_KEYS

client = TestClient(fastapi_app)


def _admin_headers(db, code):
    u = User(email=f"rr_{code}@test.local", password_hash=hash_password("x"),
             name="費率編輯測試管理員", role="admin", user_code=code)
    db.add(u)
    db.flush()
    return {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "role": "admin", "name": u.name})}


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


class TestRateRuleEditorGuards:
    """費率規則編輯器的寫入閘門（09 §3.5）。

    編輯器是唯一會讓「人」直接寫費率規則的地方，而 rule_matches 的寬容跳過
    讓一個打錯的條件鍵變成一條命中全部的規則。所以寫入端必須把讀取端刻意
    放掉的那些錯誤全部擋回來——否則這個編輯器就是一台靜默改錯價的機器。
    """

    def _plan(self, db, code):
        from app.institution.models.contract import InstContract
        from app.institution.models.plan import InstPlan
        from app.models.institution import Institution

        inst = Institution(name=f"費率編輯測試{code}", code=code)
        db.add(inst)
        db.flush()
        c = InstContract(institution_id=inst.id, name="測試合約", is_active=True)
        db.add(c)
        db.flush()
        p = InstPlan(contract_id=c.id, name="測試方案", quota_unit="count")
        db.add(p)
        db.flush()
        db.add(InstRateRule(plan_id=p.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="原本的"))
        db.commit()
        return p.id

    def _put(self, headers, plan_id, rules):
        return client.put(f"/institution/plans/{plan_id}/rate-rules", headers=headers, json={"rules": rules})

    def test_unknown_condition_key_is_rejected(self, db, http_db):
        """少一個 s 的 sesion_type——讀取端會放過，寫入端必須擋。"""
        headers = _admin_headers(db, "ARE01")
        pid = self._plan(db, "RE01")
        r = self._put(headers, pid, [
            {"sort_order": 1, "when": {"sesion_type": "online"}, "unit_price": 999, "case_payable": 0},
        ])
        assert r.status_code == 400, r.text
        assert "sesion_type" in r.json()["detail"]
        # 原本的規則要原封不動
        db.expire_all()
        rules = db.query(InstRateRule).filter(InstRateRule.plan_id == pid).all()
        assert len(rules) == 1 and rules[0].label == "原本的"

    def test_catch_all_before_others_is_rejected(self, db, http_db):
        """先匹配先贏：空條件排在前面，後面的規則永遠輪不到。"""
        headers = _admin_headers(db, "ARE02")
        pid = self._plan(db, "RE02")
        r = self._put(headers, pid, [
            {"sort_order": 1, "when": {}, "unit_price": 1600, "case_payable": 0, "label": "其餘情況"},
            {"sort_order": 2, "when": {"consult_type": "family"}, "unit_price": 2400, "case_payable": 0},
        ])
        assert r.status_code == 400, r.text
        assert "其餘情況" in r.json()["detail"]

    def test_fixed_price_without_amount_is_rejected(self, db, http_db):
        """fixed 沒填金額 → resolve_rate 回 unit_price=None，報價會變 0。"""
        headers = _admin_headers(db, "ARE03")
        pid = self._plan(db, "RE03")
        r = self._put(headers, pid, [
            {"sort_order": 1, "when": {}, "price_source": "fixed", "unit_price": None, "case_payable": 0},
        ])
        assert r.status_code == 400, r.text
        assert "鐘點費" in r.json()["detail"]

    def test_empty_rule_list_is_rejected(self, db, http_db):
        headers = _admin_headers(db, "ARE04")
        pid = self._plan(db, "RE04")
        assert self._put(headers, pid, []).status_code == 400

    def test_valid_replace_swaps_the_whole_list(self, db, http_db):
        headers = _admin_headers(db, "ARE05")
        pid = self._plan(db, "RE05")
        r = self._put(headers, pid, [
            {"sort_order": 1, "when": {"visit_seq": 1}, "unit_price": 1600, "case_payable": 0, "label": "第一次"},
            {"sort_order": 2, "when": {"visit_seq": {"gte": 2}}, "unit_price": 1400, "case_payable": 200, "label": "第二次起"},
            {"sort_order": 99, "when": {}, "unit_price": 1400, "case_payable": 200, "label": "其餘情況"},
        ])
        assert r.status_code == 200, r.text
        db.expire_all()
        rules = sorted(db.query(InstRateRule).filter(InstRateRule.plan_id == pid).all(), key=lambda x: x.sort_order)
        assert [x.label for x in rules] == ["第一次", "第二次起", "其餘情況"]
        # 整份取代：原本那條不該還留著
        assert "原本的" not in [x.label for x in rules]

        # 存進去的規則真的會被報價引擎照這個順序讀出來
        payload = [
            {"id": x.id, "sort_order": x.sort_order, "when_json": x.when_json,
             "unit_price": x.unit_price, "case_payable": x.case_payable, "price_source": x.price_source}
            for x in rules
        ]
        assert resolve_rate(payload, RateRuleContext(visit_seq=1)).unit_price == Decimal("1600")
        assert resolve_rate(payload, RateRuleContext(visit_seq=5)).unit_price == Decimal("1400")

    def test_therapist_rate_needs_no_amount(self, db, http_db):
        """聊心茶室那種直接採心理師鐘點費的方案，本來就不填 unit_price。"""
        headers = _admin_headers(db, "ARE06")
        pid = self._plan(db, "RE06")
        r = self._put(headers, pid, [
            {"sort_order": 1, "when": {}, "price_source": "therapist_rate", "unit_price": None, "case_payable": 0},
        ])
        assert r.status_code == 200, r.text

    def test_unknown_condition_keys_helper(self):
        assert unknown_condition_keys({"session_type": "online"}) == []
        assert unknown_condition_keys({"sesion_type": "x", "zzz": 1}) == ["sesion_type", "zzz"]
        assert unknown_condition_keys({}) == []
