"""個案自付款的統一判準 — V2升級計畫 09 §1.4a / §5。

裁示的核心是「分界不是自費案 vs 機構案，而是**這筆錢的付款方是誰**」：
一筆機構預約產生兩段各自獨立的錢，個案自付那段走日常收款動線。

這裡釘住的是那條規則本身，特別是兩條路徑**真值來源不同**這件事：

    機構案 —— 只認 copay_collected_at。它的 payment_status 語意是「機構請款
              進度」，跟個案付錢了沒無關。
    純自費 —— 認 copay_collected_at 或舊的 payment_status（舊端點
              PUT /ledger/{id}/pay 只寫後者）。

實測抓到的錯：dashboard 待辦原本寫成兩者 AND，於是「機構請款已完成、但個案
自付額還沒收」那種紀錄（4 筆、各 $400）永遠不會出現在待辦裡。
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.auth.password import hash_password
from app.models.case import Case
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.copay import outstanding_query, outstanding_total

TODAY = date(2026, 5, 20)


@pytest.fixture()
def env(db):
    ther = User(email="cp_t@test.local", password_hash=hash_password("x"),
                name="自付款測試心理師", role="therapist", user_code="T840",
                commission_rate=Decimal("0.70"))
    db.add(ther)
    db.flush()
    case = Case(name="自付款測試個案", therapist_id=ther.id, funding_source="self_pay",
                status="ongoing", case_number="99CP00001")
    db.add(case)
    db.flush()
    return {"db": db, "ther": ther, "case": case}


def _rec(env, **over):
    db = env["db"]
    kw = dict(
        session_date=TODAY, case_id=env["case"].id, therapist_id=env["ther"].id,
        amount=Decimal("2000"), session_type="in_person", funding_source="self_pay",
        payment_status="unpaid", copay_collected_at=None,
    )
    kw.update(over)
    r = SessionRecord(**kw)
    db.add(r)
    db.flush()
    return r


def _ids(env):
    return {r.id for r in outstanding_query(env["db"], with_relations=False)
            .filter(SessionRecord.session_date == TODAY).all()}


class TestSelfPay:
    def test_unpaid_is_outstanding(self, env):
        r = _rec(env)
        assert r.id in _ids(env)

    def test_legacy_payment_status_counts_as_collected(self, env):
        """舊端點 PUT /ledger/{id}/pay 只寫 payment_status、不寫 copay_collected_at。"""
        r = _rec(env, payment_status="paid")
        assert r.id not in _ids(env)

    def test_copay_timestamp_counts_as_collected(self, env):
        r = _rec(env, copay_collected_at=datetime.now(timezone.utc))
        assert r.id not in _ids(env)

    def test_discount_to_zero_is_not_outstanding(self, env):
        """全額優待之後就不欠錢了。舊查詢沒扣 discount_amount，會誤報。"""
        r = _rec(env, discount_amount=Decimal("2000"))
        assert r.id not in _ids(env)

    def test_void_excluded(self, env):
        r = _rec(env, is_void=True)
        assert r.id not in _ids(env)


class TestInstitution:
    def test_claimed_but_copay_uncollected_is_outstanding(self, env):
        """★ 本次修正的核心案例。

        機構請款已完成（payment_status='claimed'）不代表個案付了自付額。
        原本 dashboard 待辦用 payment_status='unpaid' 過濾，這種紀錄就消失了。
        """
        r = _rec(env, funding_source="institution", payment_status="claimed",
                 case_payable=Decimal("400"), institution_payable=Decimal("1600"))
        assert r.id in _ids(env)

    def test_copay_collected_is_not_outstanding(self, env):
        r = _rec(env, funding_source="institution", payment_status="claimed",
                 case_payable=Decimal("400"), institution_payable=Decimal("1600"),
                 copay_collected_at=datetime.now(timezone.utc))
        assert r.id not in _ids(env)

    def test_full_subsidy_owes_nothing(self, env):
        """自付額 $0 的全額補助方案不算未收。"""
        r = _rec(env, funding_source="institution", payment_status="claimed",
                 case_payable=Decimal("0"), institution_payable=Decimal("2000"))
        assert r.id not in _ids(env)

    def test_paid_payment_status_does_not_imply_collected(self, env):
        """機構案不得拿 payment_status 當「個案付錢了沒」的依據。"""
        r = _rec(env, funding_source="institution", payment_status="paid",
                 case_payable=Decimal("400"), institution_payable=Decimal("1600"))
        assert r.id in _ids(env)


class TestTotals:
    def test_total_matches_query(self, env):
        _rec(env)                                                   # 欠 2000
        _rec(env, funding_source="institution", payment_status="claimed",
             case_payable=Decimal("400"), institution_payable=Decimal("1600"))  # 欠 400
        _rec(env, payment_status="paid")                            # 已收
        n, amt = outstanding_total(env["db"], on_date=TODAY)
        assert n == 2
        assert amt == pytest.approx(2400.0)
