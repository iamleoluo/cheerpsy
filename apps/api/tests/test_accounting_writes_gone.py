"""帳務拆除上線 A（階段 2）：帳務寫入端點一律回 410，讀取端點保留。

只改路由層：不動 settlement.py、model、migration，所以也要確認 410 不會寫入任何資料。
"""

import pytest
from sqlalchemy import text

from app.main import app

D = "2026-01-01"

# (method, concrete path) — 每個都要回 410
GONE = [
    # /finance（日結、應收）
    ("POST", f"/finance/daily/{D}/close"),
    ("POST", f"/finance/daily/{D}/unlock"),
    ("POST", "/finance/ar/1/pay"),
    # 酬勞、零用金、商品
    ("POST", "/payouts/generate"),
    ("PUT", "/payouts/1/pay"),
    ("POST", "/petty-cash"),
    ("POST", "/product-sales"),
    ("PUT", "/product-sales/1/void"),
    # 核銷（claim_batches.py）
    ("POST", "/claim-batches"),
    ("PUT", "/claim-batches/1"),
    ("POST", "/claim-batches/1/records"),
    ("DELETE", "/claim-batches/1/records/1"),
    ("PUT", "/claim-batches/1/submit"),
    ("PUT", "/claim-batches/1/receive"),
    ("PUT", "/claim-batches/1/waive-docs"),
    ("POST", "/claim-batches/1/admin-verify-all"),
    ("PUT", "/claim-batches/1/unwaive-docs"),
    # 核銷（claims_extra.py）：核銷頁與心理師文件頁
    ("PUT", "/claim-batches/1/plans"),
    ("POST", "/claim-batches/1/records/1/reject"),
    ("POST", "/claim-batches/1/void"),
    ("POST", "/claim-batches/1/unlock"),
    ("POST", "/claim-batches/1/submit-claim"),
    ("POST", "/claim-batches/1/confirm-receipt"),
    ("POST", "/claim-batches/1/documents"),
    ("DELETE", "/claim-batches/1/documents/1"),
    ("POST", "/claim-batches/1/documents/upload"),
    ("POST", "/claim-batches/my/confirm-docs"),
    ("POST", "/claim-batches/my/withdraw-docs"),
    # 收據、發票
    ("POST", "/receipts/single-session/1"),
    ("POST", "/receipts/batch/1"),
    ("POST", "/receipts/product/1"),
    ("POST", "/receipts/self-pay-batch/1"),
    ("POST", "/invoices"),
    ("PUT", "/invoices/1/void"),
    # 帳冊逐筆寫入
    ("PUT", "/ledger/1/payment"),
    ("PUT", "/ledger/1/lock"),
    ("PUT", "/ledger/1/unlock"),
    ("PUT", "/ledger/1/edit"),
    ("PUT", "/ledger/1/confirm-doc"),
    ("PUT", "/ledger/1/admin-verify"),
    ("PUT", "/ledger/1/admin-unverify"),
    ("PUT", "/ledger/1/cancel-doc"),
    ("PUT", "/ledger/1/discount"),
    ("PUT", "/ledger/1/void"),
    ("POST", "/ledger/1/split"),
    ("PUT", "/ledger/1/outcall-bonus"),
    ("PUT", "/ledger/1/pay"),
    ("POST", "/ledger/pay-batch"),
    # 上線 A 第一階段已是 410
    ("POST", "/ledger/settle"),
]

# 讀取端點：保留，不可是 410（資料空時 200，不存在的 id 為 404 也可以）
STILL_READABLE = [
    "/ledger", "/ledger/pending-docs", "/ledger/confirmed-docs", "/ledger/self-pay-unpaid",
    "/ledger/self-pay-all", "/ledger/self-pay-cases",
    "/claim-batches", "/claim-batches/my/pending-docs", "/claim-batches/meta/modes",
    "/institution-contracts", "/institution-plans", "/institutions",
    "/invoices", "/petty-cash", "/payouts", "/product-sales",
    f"/finance/daily?day={D}", "/finance/ar", "/finance/monthly?month=2026-01",
    "/reports/monthly?year=2026&month=1",
]


@pytest.fixture()
def people(make_user):
    return {
        "admin": make_user("admin"),
        "accountant": make_user("accountant"),
        "staff": make_user("staff"),
        "therapist": make_user("therapist"),
    }


def _call(client, method, path, headers):
    # 不送 body：410 必須在 body 驗證（422）之前就回
    return client.request(method, path, headers=headers)


@pytest.mark.parametrize("method,path", GONE, ids=[f"{m} {p}" for m, p in GONE])
def test_write_endpoint_is_gone_for_every_role(client, auth, people, method, path):
    # /ledger/settle 本來就只有 admin 進得去（RequireRole），其他角色先被擋在 403
    roles = ["admin"] if path == "/ledger/settle" else list(people)
    for role in roles:
        r = _call(client, method, path, auth(people[role]))
        assert r.status_code == 410, f"{role}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("method,path", GONE[:6] + GONE[-3:], ids=lambda v: str(v))
def test_gone_with_valid_body_too(client, auth, people, method, path):
    r = client.request(method, path, headers=auth(people["admin"]), json={"anything": 1})
    assert r.status_code == 410


@pytest.mark.parametrize("method,path", [GONE[0], GONE[len(GONE) // 2], GONE[-1]])
def test_gone_requires_login(client, method, path):
    r = client.request(method, path)
    assert r.status_code in (401, 403)  # 未登入不洩漏「這個端點已停用」


def test_every_listed_endpoint_really_is_a_registered_route():
    """清單裡的每一筆都對應到實際路由（避免測試打到 404 而漏掉）。"""
    from fastapi.routing import APIRoute
    import re

    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    for method, path in GONE:
        hit = [r for r in routes if method in r.methods and r.path_regex.match(path)]
        assert hit, f"{method} {path} 沒有對應路由"


def test_all_write_routes_of_retired_routers_are_gone_or_explicitly_kept():
    """路由層掃描：被拆的 router 裡，凡是寫入端點，不是 410 就必須在白名單裡（刻意保留到上線 B）。"""
    from fastapi.routing import APIRoute
    from app.auth.dependencies import accounting_gone

    retired_prefixes = ("/ledger", "/invoices", "/claim-batches", "/finance", "/payouts",
                        "/petty-cash", "/product-sales", "/receipts")
    # 機構合約、方案、價目、交通費、個案額度屬「金流資訊」，已恢復，不在此列（見 test_institution_plans.py）
    kept = {  # 刻意保留的寫入端點（本階段範圍之外，上線 B 再處理）
        ("DELETE", "/petty-cash/{record_id}"),
        ("PUT", "/product-sales/{sale_id}"),
        ("PUT", "/claim-batches/records/{record_id}/amount"),
        ("PUT", "/claim-batches/{batch_id}/mode"),
    }
    missing = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith(retired_prefixes):
            continue
        for m in r.methods - {"GET", "HEAD", "OPTIONS"}:
            gone = any(d.call is accounting_gone for d in r.dependant.dependencies)
            legacy_410 = r.status_code == 410 or r.path in ("/ledger/settle",)
            if not (gone or legacy_410) and (m, r.path) not in kept:
                missing.append((m, r.path))
    assert not missing, f"還有帳務寫入端點沒改成 410：{missing}"


@pytest.mark.parametrize("path", STILL_READABLE)
def test_read_endpoints_still_work(client, auth, people, path):
    # /my/* 是心理師專用，其餘用管理員
    who = people["therapist"] if "/my/" in path else people["admin"]
    r = client.get(path, headers=auth(who))
    assert r.status_code != 410, path
    assert r.status_code in (200, 404), f"{path}: {r.status_code} {r.text[:200]}"


def test_me_payout_still_readable_for_therapist(client, auth, people):
    r = client.get("/me/payout?month=2026-01", headers=auth(people["therapist"]))
    assert r.status_code == 200, r.text


def test_gone_endpoints_write_nothing(client, auth, db, people):
    """410 不可留下任何資料：打完整份清單後，帳務相關表的筆數不變。"""
    tables = ["session_records", "invoices", "claim_batches", "petty_cash", "product_sales",
              "payouts"]
    existing = [t for t in tables
                if db.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar()]
    assert "session_records" in existing and "invoices" in existing
    before = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in existing}
    for method, path in GONE:
        client.request(method, path, headers=auth(people["admin"]), json={})
    db.expire_all()
    after = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in existing}
    assert before == after


def test_today_has_no_doc_todo(client, auth, people):
    r = client.get("/me/today", headers=auth(people["therapist"]))
    assert r.status_code == 200
    body = r.json()
    assert "pending_docs" not in body["stats"]
    assert all(t["link"] != "/docs" for t in body["todos"])
