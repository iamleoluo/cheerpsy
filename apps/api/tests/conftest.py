"""pytest 設定：對真正的 PostgreSQL 跑（預約時段用 tstzrange，SQLite 無法替代）。

用法：
    TEST_DATABASE_URL=postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test pytest apps/api/tests

TEST_DATABASE_URL 必須指向「專用的測試資料庫」：每個測試前會清空所有資料表。
連不上資料庫時整批測試會 skip，而不是失敗。
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test"
)
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
    # 現有 schema 有循環外鍵（cases↔referral_requests 等），drop_all 排序會失敗，直接重建 schema
    _reset_schema()
    Base.metadata.create_all(engine)
    yield
    _reset_schema()


def _reset_schema():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))


@pytest.fixture(autouse=True)
def _clean(_schema):
    with engine.begin() as c:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


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
