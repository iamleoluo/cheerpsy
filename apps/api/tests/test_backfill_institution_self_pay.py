"""zq7a：既有機構預約補算 self_pay_amount；算不出來就 NULL（不猜）；只動這一欄。"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import engine
from app.models.institution import Institution
from tests.test_appointment_pricing import book, make_plan, quota

API_DIR = Path(__file__).resolve().parent.parent


def _run_upgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location("zq7a", API_DIR / "alembic" / "versions" / "zq7a1b2c3d4e_backfill_institution_self_pay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()


@pytest.fixture()
def world(make_user, make_case, room, db):
    a, admin, staff = make_user("therapist", name="甲"), make_user("admin"), make_user("staff")
    c1, c2, c3 = make_case(a, "案一"), make_case(a, "案二"), make_case(a, "自費")
    for c in (c1, c2):
        c.funding_source = "institution"
    inst = Institution(name="基金會", code="ZZ")
    db.add(inst)
    db.commit()
    return dict(a=a, admin=admin, staff=staff, c1=c1, c2=c2, c3=c3, room=room, inst=inst)


def test_backfill_computes_what_it_can_and_leaves_null_otherwise(client, auth, world, db):
    w = world
    p = make_plan(client, auth, w, rate_items=[{"label": "個別", "total_amount": 1600, "self_pay_amount": 200}])
    quota(client, auth, w, w["c1"], p)
    ok = book(client, auth, w["staff"], w["c1"], w["room"], day=3).json()["id"]
    manual = book(client, auth, w["staff"], w["c1"], w["room"], day=4, amount=150).json()["id"]  # 手動調低，自付額不能超過應收
    nolink = book(client, auth, w["staff"], w["c1"], w["room"], day=5).json()["id"]  # 價目列被刪
    noplan = book(client, auth, w["staff"], w["c2"], w["room"], day=6, amount=900).json()["id"]  # 沒方案
    selfpay = book(client, auth, w["staff"], w["c3"], w["room"], day=7, amount=1800).json()["id"]

    # 還原成 zn4d 之後的舊狀態：機構預約的自付額都是預設 0
    db.execute(text("UPDATE appointments SET self_pay_amount = 0 WHERE funding_source = 'institution'"))
    db.execute(text("UPDATE appointments SET rate_item_id = NULL WHERE id = :i"), {"i": nolink})
    db.commit()
    before_amount = dict(db.execute(text("SELECT id, amount FROM appointments")).all())
    audit_before = db.execute(text("SELECT count(*) FROM audit_log")).scalar()
    tables_before = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in ("session_records", "appointments")}
    db.rollback()

    _run_upgrade()

    db.expire_all()
    got = dict(db.execute(text("SELECT id, self_pay_amount FROM appointments")).all())
    assert float(got[ok]) == 200
    assert float(got[manual]) == 150
    assert got[nolink] is None and got[noplan] is None  # 算不出來：NULL，不猜
    assert float(got[selfpay]) == 1800  # 自費不動
    assert dict(db.execute(text("SELECT id, amount FROM appointments")).all()) == before_amount  # amount 不動
    assert db.execute(text("SELECT count(*) FROM audit_log")).scalar() == audit_before  # 不寫稽核
    assert {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables_before} == tables_before

    # 重跑結果一樣（可重複執行）；先放掉讀取交易，免得 ALTER TABLE 等鎖
    db.rollback()
    _run_upgrade()
    db.expire_all()
    assert dict(db.execute(text("SELECT id, self_pay_amount FROM appointments")).all())[ok] == 200


def test_null_self_pay_is_safe_for_responses_and_titles(client, auth, world, db):
    from app.models.appointment import Appointment
    from app.services import gcal_titles

    w = world
    a = book(client, auth, w["staff"], w["c2"], w["room"], day=3, amount=900).json()["id"]
    db.execute(text("UPDATE appointments SET self_pay_amount = NULL WHERE id = :i"), {"i": a})
    db.commit()
    r = client.get(f"/appointments/{a}", headers=auth(w["staff"]))
    assert r.status_code == 200 and r.json()["self_pay_amount"] == 0
    assert client.put(f"/appointments/{a}", headers=auth(w["staff"]), json={"amount": 800}).status_code == 200
    db.expire_all()
    db.execute(text("UPDATE appointments SET self_pay_amount = NULL WHERE id = :i"), {"i": a})
    db.commit()
    assert "$" not in gcal_titles.event_title(db.get(Appointment, a), "type_room")
