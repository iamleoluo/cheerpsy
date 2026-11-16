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


def test_finance_info_endpoints_exist_and_collection_features_are_off(client, auth, make_user):
    paths = {getattr(r, "path", "") for r in app.routes}
    for kept in ("/institution-plans", "/institution-contracts", "/cases/{case_id}/billing-options"):
        assert kept in paths, kept
    # 收款記錄、失約費設定：端點停用（410），欄位保留
    staff = make_user("staff")
    h = auth(staff)
    assert client.put("/appointments/1/collection", headers=h, json={"payment_status": "paid"}).status_code == 410
    assert client.put("/appointments/1/no-show-fee", headers=h, json={"no_show_fee": 1}).status_code == 410
    assert client.get("/settings/no-show-fees", headers=h).status_code in (404, 405, 422)
