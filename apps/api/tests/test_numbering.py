"""配號系統（app/services/numbering.py）。06 P0 排定、08 §6 列為第一項缺口。

重點驗兩件舊寫法做不到的事：
  ① 同一天連續配號不重複（舊的 COUNT(*)+1 在 flush 之前連數兩次會拿到同一個數）
  ② 傳入歷史日期就配到歷史日期的號（舊的全部綁死 datetime.now()）
"""

from datetime import date

import pytest

from app.config import settings
from app.services import numbering


class TestNoCollisionWithinSameDay:
    def test_consecutive_receipt_numbers_are_distinct(self, db):
        d = date(2026, 3, 5)
        nos = [numbering.next_receipt_no(db, on_date=d) for _ in range(20)]
        assert len(set(nos)) == 20, "同一天連續配號不可重複"
        assert nos[0].endswith("-1") and nos[-1].endswith("-1")
        seqs = [numbering.parse_receipt_no(n)["seq"] for n in nos]
        assert seqs == sorted(seqs), "流水號要遞增"

    def test_appointment_numbers_distinct_per_therapist_day(self, db):
        d = date(2026, 3, 5)
        a = [numbering.next_appointment_number(db, on_date=d, therapist_code="T001") for _ in range(5)]
        b = [numbering.next_appointment_number(db, on_date=d, therapist_code="T002") for _ in range(5)]
        assert len(set(a + b)) == 10
        # 不同心理師各自從 001 起算
        assert a[0].endswith("-001") and b[0].endswith("-001")


class TestBackdating:
    def test_historical_date_gets_historical_number(self, db):
        """灌 12 個月歷史資料的關鍵：號碼要跟著那筆資料當時的日期。"""
        old = numbering.next_receipt_no(db, on_date=date(2025, 10, 17))
        new = numbering.next_receipt_no(db, on_date=date(2026, 9, 8))
        assert "20251017" in old
        assert "20260908" in new

    def test_case_number_uses_given_year(self, db):
        n25 = numbering.next_case_number(db, on_date=date(2025, 12, 1), national_id_last2="47")
        n26 = numbering.next_case_number(db, on_date=date(2026, 1, 5), national_id_last2="88")
        assert n25.startswith("25") and n25.endswith("47")
        assert n26.startswith("26") and n26.endswith("88")
        assert len(n25) == 8 and len(n26) == 8

    def test_referral_and_claim_numbers_follow_date(self, db):
        assert numbering.next_referral_code(db, on_date=date(2026, 8, 1)).startswith("260801")
        assert numbering.next_claim_no(db, on_date=date(2026, 7, 1)).startswith("202607-")


class TestReceiptFormat:
    def test_v7_format_shape(self, db):
        no = numbering.next_receipt_no(db, on_date=date(2026, 8, 1), category="C")
        parsed = numbering.parse_receipt_no(no)
        assert parsed["format"] == "v7"
        assert parsed["venue"] == "A"
        assert parsed["date"] == "20260801"
        assert parsed["category"] == "C"
        assert parsed["state"] == numbering.RECEIPT_STATE_ISSUED

    def test_reprint_and_void_share_the_base(self, db):
        issued = numbering.next_receipt_no(db, on_date=date(2026, 8, 1))
        reprint = numbering.receipt_variant(issued, numbering.RECEIPT_STATE_REPRINT)
        void = numbering.receipt_variant(issued, numbering.RECEIPT_STATE_VOID)
        assert reprint.endswith("-2") and void.endswith("-3")
        base = lambda s: s.rsplit("-", 1)[0]
        assert base(issued) == base(reprint) == base(void), "重印/作廢沿用同一個 base，重印軌跡才成立"

    def test_category_has_its_own_serial(self, db):
        d = date(2026, 8, 1)
        c = numbering.next_receipt_no(db, on_date=d, category="C")
        o = numbering.next_receipt_no(db, on_date=d, category="O")
        assert numbering.parse_receipt_no(c)["seq"] == numbering.parse_receipt_no(o)["seq"] == 1

    def test_legacy_format_switch(self, db, monkeypatch):
        """01 §C4 這條規則還沒定案，所以格式必須切得回去。"""
        monkeypatch.setattr(settings, "RECEIPT_NUMBER_FORMAT", "legacy")
        no = numbering.next_receipt_no(db, on_date=date(2026, 8, 1))
        assert no.startswith("R20260801")
        assert numbering.parse_receipt_no(no)["format"] == "legacy"

    def test_parser_tolerates_split_suffix(self, db):
        """ledger 拆帳會在收據號後面加 -A / -B，解析器要看得懂。"""
        issued = numbering.next_receipt_no(db, on_date=date(2026, 8, 1))
        parsed = numbering.parse_receipt_no(f"{issued}-B")
        assert parsed is not None and parsed["split"] == "B"

    def test_unparseable_returns_none(self, db):
        assert numbering.parse_receipt_no("這不是收據號") is None
        assert numbering.parse_receipt_no("") is None


class TestBackfillFromExistingRows:
    def test_first_touch_continues_from_existing_data(self, db):
        """掛到既有資料庫上不可以從 1 重來——否則第一批號碼全部撞 unique。"""
        from app.models.case import Case
        from app.models.user import User
        from app.auth.password import hash_password

        t = User(email="numbering_t@test.local", password_hash=hash_password("x"),
                 name="配號測試心理師", role="therapist", user_code="T995")
        db.add(t)
        db.flush()
        # 先手動塞一筆 25 年度、流水號 0042 的病歷號，模擬既有資料
        db.add(Case(name="既有個案", therapist_id=t.id, status="ongoing", case_number="25004299"))
        db.flush()

        got = numbering.next_case_number(db, on_date=date(2025, 6, 1), national_id_last2="11")
        assert got == "25004311", f"應接續既有最大流水號 0042 之後，實得 {got}"
