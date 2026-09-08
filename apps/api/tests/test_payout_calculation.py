"""心理師酬勞計算（07 §8.2）。這支是純函式測試，不碰 HTTP。

原本 payouts.py 對每一筆場次都套同一條「金額 × 抽成率 ＋ 外出保底」，
結果三種薪酬模式全部算錯，而且錯的方向不一樣：

  · kickback（回扣制）：診所抽的那份應該由心理師回繳，是**扣項**。
    舊寫法把它當成正的抽成，等於診所倒過來付一筆錢出去。
  · none（借場地，無心理師勞務）：不該計酬，舊寫法照算。
  · 作廢紀錄：舊寫法沒有濾掉 is_void，作廢的場次照樣發錢。
  · commissionable_base（可抽成基數，排除交通費那類不抽成的部分）
    存了但沒人讀；優待減免也沒有從基數扣掉。
"""

from decimal import Decimal

from app.models.session_record import SessionRecord
from app.routers.payouts import payout_line_amount


def _sr(**kw):
    defaults = dict(amount=Decimal("2000"), commission_rate_used=Decimal("0.70"),
                    compensation_mode="commission", is_void=False, discount_amount=Decimal("0"),
                    outcall_bonus=Decimal("0"), commissionable_base=None)
    defaults.update(kw)
    return SessionRecord(**defaults)


class TestCommission:
    def test_plain_commission(self):
        assert payout_line_amount(_sr()) == Decimal("1400.00")

    def test_discount_reduces_the_base(self):
        # 優待 200 → 基數 1800 × 0.7
        assert payout_line_amount(_sr(discount_amount=Decimal("200"))) == Decimal("1260.00")

    def test_commissionable_base_wins_over_amount(self):
        """報價當下算好的可抽成基數優先——例如總額含 400 交通費不抽成。"""
        got = payout_line_amount(_sr(amount=Decimal("2400"), commissionable_base=Decimal("2000")))
        assert got == Decimal("1400.00")

    def test_outcall_bonus_added(self):
        got = payout_line_amount(_sr(amount=Decimal("1000"), outcall_bonus=Decimal("300")))
        assert got == Decimal("1000.00")  # 1000*0.7 + 300


class TestKickback:
    def test_kickback_is_a_deduction(self):
        """回扣制：鐘點費心理師自己收，診所那 30% 要回繳 → 對酬勞是負的。"""
        got = payout_line_amount(_sr(amount=Decimal("2000"), compensation_mode="kickback"))
        assert got == Decimal("-600.00")

    def test_kickback_uses_commissionable_base(self):
        got = payout_line_amount(_sr(amount=Decimal("2400"), commissionable_base=Decimal("2000"),
                                     compensation_mode="kickback"))
        assert got == Decimal("-600.00")


class TestNoneAndVoid:
    def test_no_labour_mode_pays_nothing(self):
        assert payout_line_amount(_sr(compensation_mode="none")) == Decimal("0")

    def test_void_pays_nothing_regardless_of_mode(self):
        assert payout_line_amount(_sr(is_void=True)) == Decimal("0")
        assert payout_line_amount(_sr(is_void=True, compensation_mode="kickback")) == Decimal("0")

    def test_null_mode_defaults_to_commission(self):
        """舊資料沒有 compensation_mode（自費案本來就不會有），要當抽成制。"""
        assert payout_line_amount(_sr(compensation_mode=None)) == Decimal("1400.00")


class TestMixedMonth:
    def test_kickback_offsets_commission_in_the_same_month(self):
        """同一位心理師同月混合三種模式，總額要能互相沖銷。"""
        rows = [
            _sr(amount=Decimal("2000")),                                        # +1400
            _sr(amount=Decimal("2000"), compensation_mode="kickback"),          # -600
            _sr(amount=Decimal("500"), compensation_mode="none"),               # 0
            _sr(amount=Decimal("2000"), is_void=True),                          # 0
        ]
        assert sum(payout_line_amount(r) for r in rows) == Decimal("800.00")
