"""pytest 設定：對真正的 PostgreSQL 跑（預約時段用 tstzrange，SQLite 無法替代）。

用法：
    TEST_DATABASE_URL=postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test pytest apps/api/tests
    pytest -n auto apps/api/tests          # 平行：每個 worker 用自己的資料庫 <名稱>_<worker>（不存在就建立）
    pytest -m "not slow" apps/api/tests    # 跳過跑 migration 的慢測試
    REUSE_TEST_SCHEMA=1 pytest tests/test_x.py   # 開發中跑少數檔案：schema 已是最新就不重建（預設不開，完整流程不受影響）

TEST_DATABASE_URL 必須指向「專用的測試資料庫」。
資料隔離：每個測試包在外層 transaction + SAVEPOINT 裡，結束時整個 rollback（比 TRUNCATE 快很多）。
需要真的 commit 的測試（獨立連線、子程序、執行緒、跑 migration）標 @pytest.mark.real_commit，
它們改用 TRUNCATE（測試前後各一次）。連不上資料庫時整批測試會 skip，而不是失敗。
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test"
)


def _per_worker_url(url: str) -> str:
    """pytest-xdist 下每個 worker 用自己的資料庫 <名稱>_<worker>，不存在就建立。"""
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return url
    from urllib.parse import urlsplit, urlunsplit

    import psycopg2

    parts = urlsplit(url)
    base = (parts.path or "/").lstrip("/") or "cheerpsy_test"
    name = f"{base}_{worker}"
    try:
        admin = urlunsplit(parts._replace(path="/postgres"))
        conn = psycopg2.connect(admin)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{name}"')
        conn.close()
    except Exception:  # 連不上時交給 _schema 統一 skip
        pass
    return urlunsplit(parts._replace(path=f"/{name}"))


# 開發用：REUSE_TEST_SCHEMA=1 時，資料庫裡的 schema 若與目前的 model 完全一致就沿用，不 DROP／重建，結束也不清掉。
# 預設（含 CI 與完整 -n auto 流程）不開，行為與以前完全相同。
REUSE_SCHEMA = os.environ.get("REUSE_TEST_SCHEMA") == "1"

TEST_DB_URL = _per_worker_url(TEST_DB_URL)
# 必須在 import app 之前設定，app.database 會在 import 時建立 engine
os.environ["DATABASE_URL"] = TEST_DB_URL

from sqlalchemy import text  # noqa: E402

from app.auth.jwt import create_access_token  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401  註冊所有 model
from app.models.notification import Notification  # noqa: E402,F401
from app.models.appointment import Appointment  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.room import Room  # noqa: E402
from app.models.user import User  # noqa: E402
from psycopg2.extras import DateTimeTZRange  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"測試資料庫連不上（{TEST_DB_URL}）：{e}", allow_module_level=False)
    if REUSE_SCHEMA and _schema_is_current():
        _truncate_all()  # 上次被中斷時可能留下資料
    else:
        # 現有 schema 有循環外鍵（cases↔referral_requests 等），drop_all 排序會失敗，直接重建 schema
        _reset_schema()
        Base.metadata.create_all(engine)
        if REUSE_SCHEMA:
            _store_fingerprint()
    yield
    if not REUSE_SCHEMA:
        _reset_schema()


_FP_TABLE = "_test_schema_fingerprint"


def _schema_fingerprint() -> str:
    """目前所有 model 的結構雜湊（欄位、型別、可空、預設、約束、索引）；任何異動都會不同。
    刻意不用 CreateTable 的 DDL 文字：約束的輸出順序在不同 process 間不固定，會讓雜湊每次都變。"""
    from sqlalchemy.dialects import postgresql

    d = postgresql.dialect()
    lines = []
    for t in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        for c in t.columns:  # 欄位順序固定（宣告順序）
            default = c.server_default.arg if c.server_default is not None else None
            lines.append(f"{t.name}.{c.name}|{c.type.compile(dialect=d)}|{c.nullable}|{c.primary_key}|{default}")
        cons = []
        for k in t.constraints:
            cols = ",".join(sorted(x.name for x in getattr(k, "columns", [])))
            extra = str(getattr(k, "sqltext", "")) if k.__class__.__name__ == "CheckConstraint" else ""
            if k.__class__.__name__ == "ForeignKeyConstraint":
                extra = ",".join(sorted(e.target_fullname for e in k.elements))
            cons.append(f"{k.__class__.__name__}|{k.name}|{cols}|{extra}")
        lines.extend(f"{t.name}!{x}" for x in sorted(cons))
        lines.extend(
            f"{t.name}#{i.name}|{','.join(sorted(x.name for x in i.columns))}|{i.unique}" for i in sorted(t.indexes, key=lambda i: i.name or "")
        )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _schema_is_current() -> bool:
    try:
        with engine.connect() as c:
            stored = c.execute(text(f"SELECT fp FROM {_FP_TABLE}")).scalar()
            have = {r[0] for r in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
    except Exception:
        return False
    want = set(Base.metadata.tables) | {_FP_TABLE}
    return stored == _schema_fingerprint() and have == want


def _store_fingerprint() -> None:
    with engine.begin() as c:
        c.execute(text(f"CREATE TABLE {_FP_TABLE} (fp text NOT NULL)"))
        c.execute(text(f"INSERT INTO {_FP_TABLE} (fp) VALUES (:fp)"), {"fp": _schema_fingerprint()})


def _reset_schema():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))


def _truncate_all():
    with engine.begin() as c:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _clean(_schema, request):
    if request.node.get_closest_marker("real_commit"):
        # 要真的 commit（獨立連線／子程序／執行緒／migration）：用 TRUNCATE，前後各一次，不留資料給後面的測試
        _truncate_all()
        try:
            yield
        finally:
            _truncate_all()
        return
    # 預設：所有 session（測試的 db 與 app 請求）共用同一條連線，包在外層 transaction 裡；
    # session.commit() 只釋放 SAVEPOINT，測試結束整個 rollback。
    conn = engine.connect()
    outer = conn.begin()
    SessionLocal.configure(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield
    finally:
        SessionLocal.kw.pop("join_transaction_mode", None)
        SessionLocal.configure(bind=engine)
        outer.rollback()
        conn.close()


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ---- 資料工廠 -------------------------------------------------------------
_counter = {"n": 0}


def _n() -> int:
    _counter["n"] += 1
    return _counter["n"]


@pytest.fixture()
def make_user(db):
    def _make(role: str, name: str | None = None, **kw) -> User:
        n = _n()
        u = User(
            email=f"{role}{n}@test.local",
            password_hash="x",
            name=name or f"{role}-{n}",
            role=role,
            user_code=kw.pop("user_code", f"{role[0].upper()}{n:03d}"),
            **kw,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    return _make


@pytest.fixture()
def auth():
    def _auth(user: User) -> dict:
        tok = create_access_token({"sub": str(user.id), "role": user.role, "name": user.name})
        return {"Authorization": f"Bearer {tok}"}

    return _auth


@pytest.fixture()
def room(db):
    r = Room(name="晤談室 2B", floor=2, room_code="2B")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def make_case(db):
    def _make(therapist: User, name: str, **kw) -> Case:
        c = Case(
            name=name,
            therapist_id=therapist.id,
            phone=kw.pop("phone", "0912-345-678"),
            chief_complaint=kw.pop("chief_complaint", "憂鬱與失眠"),
            status=kw.pop("status", "ongoing"),
            **kw,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    return _make


@pytest.fixture()
def make_appt(db):
    def _make(case: Case, therapist: User, room: Room | None, start: datetime | None = None,
              hours: int = 1, status: str = "booked", session_type: str = "in_person",
              is_intake: bool = False) -> Appointment:
        n = _n()
        start = start or (datetime.now(timezone.utc) + timedelta(days=2, hours=n))
        a = Appointment(
            appointment_number=f"R-TEST-{n:04d}",
            case_id=case.id if case else None,
            therapist_id=therapist.id,
            room_id=room.id if room else None,
            session_type=session_type,
            time_range=DateTimeTZRange(start, start + timedelta(hours=hours)),
            amount=1500,
            status=status,
            is_intake=is_intake,
        )
        db.add(a)
        db.commit()
        db.refresh(a)
        return a

    return _make
