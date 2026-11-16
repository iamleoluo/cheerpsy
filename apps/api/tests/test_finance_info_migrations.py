"""金流資訊（方案、額度、收款、失約費）的 migration 只新增欄位，不刪表、不刪資料；核銷對帳維持移除（已移除端點的 410 由 test_accounting_writes_gone 守住）。"""

import re
from pathlib import Path

from app.main import app

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
NEW = [
    "zn4d8e9f0a1b_appointment_self_pay_amount.py",
    "zo5e9f0a1b2c_appointment_payment_record.py",
    "zp6f0a1b2c3d_no_show_fee_settings.py",
]


def test_migrations_are_chained_and_only_add_columns():
    revs = []
    for name in NEW:
        txt = (VERSIONS / name).read_text(encoding="utf-8")
        up = txt.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
        assert "drop_table" not in up and "drop_column" not in up and "DELETE FROM" not in up.upper()
        revs.append((re.search(r'^revision = "(\w+)"', txt, re.M).group(1), re.search(r'^down_revision = "(\w+)"', txt, re.M).group(1)))
    assert revs[0][1] == "zm3c7d8e9f0a" and revs[1][1] == revs[0][0] and revs[2][1] == revs[1][0]


def test_finance_info_endpoints_exist():
    paths = {getattr(r, "path", "") for r in app.routes}
    # 金流資訊的端點存在
    for kept in ("/institution-plans", "/institution-contracts", "/cases/{case_id}/billing-options",
                 "/appointments/{appointment_id}/collection", "/appointments/{appointment_id}/no-show-fee",
                 "/settings/no-show-fees"):
        assert kept in paths, kept
