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
    assert r.status_code == 200 and r.json()["self_pay_amount"] is None  # 未設定
    assert client.put(f"/appointments/{a}", headers=auth(w["staff"]), json={"amount": 800}).status_code == 200
    db.expire_all()
    db.execute(text("UPDATE appointments SET self_pay_amount = NULL WHERE id = :i"), {"i": a})
    db.commit()
    assert gcal_titles.event_title(db.get(Appointment, a), "type_room").endswith("$800（自付未設定）")


def _run_zt0d():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location(
        "zt0d", API_DIR / "alembic" / "versions" / "zt0d4e5f6a7b_backfill_self_pay_from_session_records.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()


def test_backfill_prefers_session_records_then_rate_item_then_null(client, auth, world, db):
    """zt0d：session_records（is_void=false）優先；claim>0 且自付 0＝全額補助存 0；其次價目項目；都沒有 NULL。"""
    w = world
    p = make_plan(client, auth, w, rate_items=[{"label": "個別", "total_amount": 1600, "self_pay_amount": 200}])
    quota(client, auth, w, w["c1"], p)
    ids = {k: book(client, auth, w["staff"], w["c1"], w["room"], day=d).json()["id"]
           for k, d in (("paid", 3), ("full", 4), ("void", 5), ("rate", 6), ("zero", 7))}
    noplan = book(client, auth, w["staff"], w["c2"], w["room"], day=8, amount=900).json()["id"]

    def rec(appt, self_pay, claim, void=False):
        db.execute(text("""
            INSERT INTO session_records (appointment_id, session_date, therapist_id, session_type, amount,
                                         self_pay_amount, institution_claim_amount, is_void,
                                         fee_category, payment_status)
            SELECT id, current_date, therapist_id, session_type, amount, :sp, :cl, :v,
                   'counseling', 'unpaid' FROM appointments WHERE id = :i
        """), {"i": appt, "sp": self_pay, "cl": claim, "v": void})

    rec(ids["paid"], 300, 1300)       # 實際自付 300（價目是 200）→ 採用 300
    rec(ids["full"], 0, 1600)         # 全額補助 → 0
    rec(ids["void"], 999, 601, True)  # 作廢的不採用 → 退回價目 200
    rec(ids["zero"], 0, 0)            # 沒有可靠資訊 → 退回價目 200
    db.execute(text("UPDATE appointments SET self_pay_amount = NULL WHERE funding_source = 'institution'"))
    db.commit()
    before_amount = dict(db.execute(text("SELECT id, amount FROM appointments")).all())
    db.rollback()

    _run_zt0d()

    db.expire_all()
    got = dict(db.execute(text("SELECT id, self_pay_amount FROM appointments")).all())
    assert float(got[ids["paid"]]) == 300
    assert float(got[ids["full"]]) == 0
    assert float(got[ids["void"]]) == 200
    assert float(got[ids["rate"]]) == 200
    assert float(got[ids["zero"]]) == 200
    assert got[noplan] is None
    assert dict(db.execute(text("SELECT id, amount FROM appointments")).all()) == before_amount
    db.rollback()


def test_check_amounts_script_lists_problem_rows_read_only(client, auth, world, db, tmp_path):
    import os, subprocess, sys

    w = world
    p = make_plan(client, auth, w, rate_items=[{"label": "個別", "total_amount": 1600, "self_pay_amount": 200}])
    quota(client, auth, w, w["c1"], p)
    good = book(client, auth, w["staff"], w["c1"], w["room"], day=3).json()["id"]
    unset = book(client, auth, w["staff"], w["c2"], w["room"], day=4, amount=900).json()["id"]  # 沒方案 → 自付 NULL
    zero = book(client, auth, w["staff"], w["c3"], w["room"], day=5, amount=1800).json()["id"]
    db.execute(text("UPDATE appointments SET amount = 0 WHERE id = :i"), {"i": zero})
    db.commit()
    snapshot = db.execute(text("SELECT id, amount, self_pay_amount FROM appointments ORDER BY id")).all()
    db.rollback()

    env = {**os.environ, "DATABASE_URL": str(engine.url.render_as_string(hide_password=False)), "PYTHONUTF8": "1"}
    r = subprocess.run([sys.executable, "-X", "utf8", str(API_DIR / "scripts" / "check_amounts.py"), "--strict"],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 1, r.stderr
    assert f"#{unset}\t" in r.stdout and "自付額未設定" in r.stdout
    assert f"#{zero}\t" in r.stdout and "金額為 0" in r.stdout
    assert f"#{good}\t" not in r.stdout
    assert db.execute(text("SELECT id, amount, self_pay_amount FROM appointments ORDER BY id")).all() == snapshot  # 唯讀


def test_duplicate_valid_session_records_use_latest_and_are_listed_by_check_script(client, auth, world, db):
    import os, subprocess, sys

    w = world
    p = make_plan(client, auth, w, rate_items=[{"label": "個別", "total_amount": 1600, "self_pay_amount": 200}])
    quota(client, auth, w, w["c1"], p)
    a = book(client, auth, w["staff"], w["c1"], w["room"], day=3).json()["id"]

    # 若資料庫對 appointment_id 有唯一限制，重複根本寫不進去；這裡只在允許時才驗（舊資料可能有）
    def rec(sp, cl):
        db.execute(text("""
            INSERT INTO session_records (appointment_id, session_date, therapist_id, session_type, amount,
                                         self_pay_amount, institution_claim_amount, is_void, fee_category, payment_status)
            SELECT id, current_date, therapist_id, session_type, amount, :sp, :cl, false, 'counseling', 'unpaid'
              FROM appointments WHERE id = :i
        """), {"i": a, "sp": sp, "cl": cl})

    # 這個測試庫對 appointment_id 有唯一限制；為了模擬舊資料，暫時拿掉，測完還原
    cons = db.execute(text("""
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'session_records'::regclass AND c.contype = 'u'
           AND (SELECT array_agg(a.attname::text) FROM pg_attribute a
                 WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)) = ARRAY['appointment_id']
    """)).scalars().all()
    for n in cons:
        db.execute(text(f'ALTER TABLE session_records DROP CONSTRAINT "{n}"'))
    db.commit()
    try:
        rec(500, 1100)
        rec(300, 1300)
        db.commit()
        db.execute(text("UPDATE appointments SET self_pay_amount = NULL WHERE id = :i"), {"i": a})
        db.commit()
        db.rollback()
        _run_zt0d()
        db.expire_all()
        assert float(db.execute(text("SELECT self_pay_amount FROM appointments WHERE id = :i"), {"i": a}).scalar()) == 300  # 最新一筆

        env = {**os.environ, "DATABASE_URL": str(engine.url.render_as_string(hide_password=False)), "PYTHONUTF8": "1"}
        r = subprocess.run([sys.executable, "-X", "utf8", str(API_DIR / "scripts" / "check_amounts.py")],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        assert f"#{a}	" in r.stdout and "多筆有效 session_records" in r.stdout
    finally:
        db.rollback()
        db.execute(text("DELETE FROM session_records WHERE appointment_id = :i"), {"i": a})
        for n in cons:
            db.execute(text(f'ALTER TABLE session_records ADD CONSTRAINT "{n}" UNIQUE (appointment_id)'))
        db.commit()
