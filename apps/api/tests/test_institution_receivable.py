"""機構應收的跨機構唯讀檢視 —— V2升級計畫 09 §4.2。

應收帳冊第三分頁。前兩頁講個案自己要付的錢，這頁講機構要撥給診所的那一段。

要回答的是「機構那邊還有多少錢沒進來」，而那是**兩段不同的錢**：

    已送出等撥款  已經開單請款了，在等對方付
    尚未收納      做完了但還沒被任何核銷案撈進去 —— **還沒開始要錢**

第二段是行政最容易漏的（07 §4.3 建議做成常駐檢視），所以這裡釘住的重點是：
已收納的不能算進去、自付額不能算進去、跨月的要標出來。
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.auth.password import hash_password
from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.receivable import institution_receivable
from app.models.session_record import SessionRecord
from app.models.user import User

TODAY = date(2026, 6, 20)


@pytest.fixture()
def env(db):
    t = User(email="rcv_t@test.local", password_hash=hash_password("x"),
             name="應收測試心理師", role="therapist", user_code="T850",
             commission_rate=Decimal("0.70"))
    db.add(t)
    db.flush()
    return {"db": db, "ther": t}


def _rec(env, *, inst_payable, session_date=TODAY, funding="institution"):
    r = SessionRecord(
        session_date=session_date, therapist_id=env["ther"].id,
        amount=Decimal("2000"), session_type="in_person", funding_source=funding,
        payment_status="unpaid", institution_payable=inst_payable,
    )
    env["db"].add(r)
    env["db"].flush()
    return r


def _uncollected_total(env):
    return institution_receivable(env["db"], today=TODAY)["summary"]["uncollected_total"]


class TestUncollected:
    def test_counts_institution_payable_not_yet_claimed(self, env):
        before = _uncollected_total(env)
        _rec(env, inst_payable=Decimal("1600"))
        assert _uncollected_total(env) == pytest.approx(before + 1600)

    def test_excludes_records_already_in_a_claim_case(self, env):
        db = env["db"]
        before = _uncollected_total(env)
        r = _rec(env, inst_payable=Decimal("1600"))
        cc = InstClaimCase(claim_no="TST-01", claim_group_key="k", status="collecting")
        db.add(cc)
        db.flush()
        db.add(InstClaimLine(claim_case_id=cc.id, session_record_id=r.id,
                             claimed_amount=Decimal("1600")))
        db.flush()
        # 已經被容器收走了，就不算「還沒開始要」
        assert _uncollected_total(env) == pytest.approx(before)

    def test_ignores_self_pay(self, env):
        """自付額走另一條流程（09 §1.4a），不屬於機構應收。"""
        before = _uncollected_total(env)
        _rec(env, inst_payable=None, funding="self_pay")
        assert _uncollected_total(env) == pytest.approx(before)

    def test_flags_stale_across_month(self, env):
        """跨月遺留＝拖過一個月還沒開單，是這頁最該處理的東西。"""
        _rec(env, inst_payable=Decimal("900"), session_date=TODAY - timedelta(days=60))
        res = institution_receivable(env["db"], today=TODAY)
        assert any(u["is_stale"] for u in res["uncollected"])


class TestAwaitingPayment:
    def test_submitted_case_appears(self, env):
        db = env["db"]
        cc = InstClaimCase(claim_no="TST-02", claim_group_key="k",
                           status="submitted", applied_amount=Decimal("5000"))
        db.add(cc)
        db.flush()
        res = institution_receivable(db, today=TODAY)
        assert any(a["claim_no"] == "TST-02" for a in res["awaiting_payment"])
        assert res["summary"]["awaiting_total"] >= 5000

    def test_voided_case_excluded(self, env):
        from datetime import datetime, timezone

        db = env["db"]
        cc = InstClaimCase(claim_no="TST-03", claim_group_key="k", status="submitted",
                           applied_amount=Decimal("5000"),
                           voided_at=datetime.now(timezone.utc))
        db.add(cc)
        db.flush()
        res = institution_receivable(db, today=TODAY)
        assert not any(a["claim_no"] == "TST-03" for a in res["awaiting_payment"])
