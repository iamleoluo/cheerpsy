"""會計（accountant）角色已刪除（2026-11-17）：不能再建立或改成 accountant；既有帳號被 migration 停用、不能登入也不能重新啟用。"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.auth.password import hash_password
from app.database import engine
from app.models.user import User

API_DIR = Path(__file__).resolve().parent.parent


def _run_upgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location("zu1e", API_DIR / "alembic" / "versions" / "zu1e5f6a7b8c_disable_accountant_users.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()


def test_creating_an_accountant_is_rejected_with_422(client, auth, make_user):
    admin = make_user("admin")
    r = client.post("/auth/invitations", headers=auth(admin), json={"name": "會計", "role": "accountant"})
    assert r.status_code == 422
    ok = client.post("/auth/invitations", headers=auth(admin), json={"name": "行政", "role": "staff"})
    assert ok.status_code == 200


def test_changing_a_user_to_accountant_is_rejected_with_422(client, auth, make_user, db):
    admin, staff = make_user("admin"), make_user("staff")
    r = client.put(f"/auth/users/{staff.id}", headers=auth(admin), json={"role": "accountant"})
    assert r.status_code == 422
    db.refresh(staff)
    assert staff.role == "staff"


def test_existing_accountant_is_disabled_by_migration_and_cannot_log_in(client, auth, make_user, db):
    admin, therapist = make_user("admin"), make_user("therapist")
    acct = User(email="old-acct@test.local", password_hash=hash_password("pw12345678"), name="舊會計",
                role="accountant", user_code="C900")
    db.add(acct)
    db.commit()
    before_rows = db.execute(text("SELECT count(*) FROM users")).scalar()
    db.rollback()
    _run_upgrade()
    db.expire_all()
    row = db.execute(text("SELECT role, is_active FROM users WHERE email = 'old-acct@test.local'")).one()
    assert row.role == "accountant" and row.is_active is False  # 只停用：不刪、不改角色
    assert db.execute(text("SELECT count(*) FROM users")).scalar() == before_rows
    assert db.get(User, therapist.id).is_active is True and db.get(User, admin.id).is_active is True  # 別人不受影響
    r = client.post("/auth/login", json={"email": "old-acct@test.local", "password": "pw12345678"})
    assert r.status_code == 403
    # 已發出的舊 token 也不能用
    assert client.get("/auth/me", headers=auth(acct)).status_code in (401, 403)
    # 不能重新啟用
    t = client.put(f"/auth/users/{acct.id}/toggle", headers=auth(admin))
    assert t.status_code == 409
    db.rollback()
    assert db.execute(text("SELECT is_active FROM users WHERE id = :i"), {"i": acct.id}).scalar() is False
