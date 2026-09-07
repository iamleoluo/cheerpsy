"""測試用 DB fixture。

apps/api 目前沒有任何測試基礎設施（見 V2升級計畫 01 §A 的既有體質記錄），
這是第一支。刻意保持最簡單：每個測試都在一個交易裡跑，結束時 rollback，
不需要每次重建 schema，跑起來快。

需要一個真的跑著 PostgreSQL 16 的資料庫（TSTZRANGE/JSONB 用得到，SQLite
不行），schema 需已跑過 `alembic upgrade head`。預設指向
postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test ——
本機測試可用 Homebrew 裝一個：見本檔案 docstring 底部的指令。

    brew install postgresql@16
    LC_ALL="en_US.UTF-8" /opt/homebrew/opt/postgresql@16/bin/pg_ctl \\
        -D /opt/homebrew/var/postgresql@16 -l /tmp/pg16.log start
    /opt/homebrew/opt/postgresql@16/bin/createdb cheerpsy_test
    /opt/homebrew/opt/postgresql@16/bin/psql -d cheerpsy_test \\
        -c "CREATE ROLE cheerpsy WITH LOGIN PASSWORD 'cheerpsy' SUPERUSER;"
    DATABASE_URL=postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test \\
        .venv/bin/python -m alembic upgrade head
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy_test")

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db


@pytest.fixture()
def db():
    """每個測試獨立一個交易，結束時整個 rollback——測試之間不互相污染，
    也不用每次清資料表。"""
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def http_db(db):
    """給要透過 FastAPI TestClient 打 HTTP 的測試用。

    背景：TestClient 送出的請求，其 `Depends(get_db)` 預設會建一個全新的
    Session（走 app.database 的全域 engine），跟 db fixture 的獨立交易是
    「不同連線」——在 Postgres 的交易隔離下，HTTP 請求那邊完全看不到
    db fixture 建的 fixture 資料（因為還沒 commit，其他連線看不到）。

    這支 fixture 用 FastAPI 的 dependency_overrides 把 get_db 換成回傳
    「同一個」db session，讓 HTTP 請求跟測試本身共用同一筆交易，結束時
    一起 rollback。用法：測試簽名寫 `def test_x(self, db, http_db):`，
    db 用來準備 fixture／驗證，http_db 只是觸發 override 生效（不用讀值）。
    """
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
