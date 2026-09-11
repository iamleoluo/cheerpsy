"""場地費從酬勞扣回 —— 07 §8.2（督導模式 A/B）· 06 P6 · 09 §4.3 的 C 區。

    模式 A  櫃台代收督導費、開立收據，**場地費自動 $0**（診所收的是督導費）
    模式 B  心理師自收督導費，**場地費照收並由酬勞回扣**

10 §7.1 原本把這件事標成「部分完成：計算與場地租借的連結已建，酬勞單上的
扣回明細列尚未呈現」。實際查證後更嚴重——`generate_payouts` 完全沒有引用
VenueRental：**不是明細沒顯示，是錢根本沒扣**，心理師被多發了他們該付的場地費
（實測假資料 2026 年少扣 $12,400）。

判準是 `payer` 而不是 `supervision_fee_mode`：未到時付款方會改成「借用人自付」
（場地已經被佔住，成本不會因為人沒來就消失），那種不從酬勞扣。
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.models.room import Room
from app.models.user import User
from app.models.venue_rental import VenueRental
from app.routers.payouts import venue_deduction_total

YEAR, MONTH = 2026, 4


@pytest.fixture()
def env(db):
    t = User(email="vd_t@test.local", password_hash=hash_password("x"),
             name="扣回測試心理師", role="therapist", user_code="T860",
             commission_rate=Decimal("0.70"))
    db.add(t)
    db.flush()
    room = Room(name="vd room", floor=1, room_code="VD-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()
    return {"db": db, "ther": t, "room": room}


def _rental(env, *, kind="private", payer="therapist", mode="B", amount="800",
            status="booked", day=10):
    start = datetime(YEAR, MONTH, day, 2, 0, tzinfo=timezone.utc)
    v = VenueRental(
        rental_no=f"V-{day}-{payer}", room_id=env["room"].id,
        time_range=DateTimeTZRange(start, start.replace(hour=4)),
        purpose="督導", renter_kind=kind, payer=payer,
        renter_name=env["ther"].name,
        renter_therapist_id=env["ther"].id if kind == "private" else None,
        supervision_fee_mode=mode, amount=Decimal(amount), status=status,
    )
    env["db"].add(v)
    env["db"].flush()
    return v


def _total(env):
    return float(venue_deduction_total(env["db"], env["ther"].id, YEAR, MONTH))


class TestDeduction:
    def test_mode_b_self_paid_is_deducted(self, env):
        _rental(env, amount="800", day=10)
        assert _total(env) == pytest.approx(800)

    def test_mode_a_has_no_fee_to_deduct(self, env):
        """模式 A 的場地費本來就是 $0——診所收的是督導費。"""
        _rental(env, mode="A", amount="0", day=11)
        assert _total(env) == pytest.approx(0)

    def test_payer_renter_not_deducted(self, env):
        """未到 → 付款方改「借用人自付」，那筆不從酬勞扣。"""
        _rental(env, payer="renter", amount="800", day=12)
        assert _total(env) == pytest.approx(0)

    def test_institution_rental_not_deducted(self, env):
        """外部機構借用 → 場地費進機構應收，跟著核銷走，與心理師酬勞無關。"""
        _rental(env, kind="institution", payer="institution", mode=None, amount="1500", day=13)
        assert _total(env) == pytest.approx(0)

    def test_cancelled_not_deducted(self, env):
        _rental(env, amount="800", status="cancelled", day=14)
        assert _total(env) == pytest.approx(0)

    def test_other_month_not_deducted(self, env):
        v = _rental(env, amount="800", day=10)
        start = datetime(YEAR, MONTH + 1, 10, 2, 0, tzinfo=timezone.utc)
        v.time_range = DateTimeTZRange(start, start.replace(hour=4))
        env["db"].flush()
        assert _total(env) == pytest.approx(0)

    def test_multiple_accumulate(self, env):
        _rental(env, amount="800", day=10)
        _rental(env, amount="1200", day=15)
        assert _total(env) == pytest.approx(2000)
