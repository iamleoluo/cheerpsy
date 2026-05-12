# CheerPsy v2 — 心理診療所營運管理系統

FastAPI + Next.js 14 全端營運管理系統。

## 架構

| 層 | 技術 | 位置 |
|---|---|---|
| 前端 | Next.js 14 (App Router) + TypeScript + Tailwind CSS | `apps/web/` |
| 後端 | FastAPI + SQLAlchemy 2.x + Pydantic v2 | `apps/api/` |
| 資料庫 | PostgreSQL 16 | Docker / Railway |
| 快取 | Redis 7 | Docker / Railway |

## 本地開發

### 前置條件

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### 啟動

```bash
# 1. 啟動資料庫
docker compose up -d

# 2. 後端
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python seed.py
uvicorn app.main:app --reload

# 3. 前端（另一個 terminal）
cd apps/web
npm install
npm run dev
```

- 前端：http://localhost:3000
- 後端 API：http://localhost:8000
- Swagger UI：http://localhost:8000/docs

### 預設帳號

| 帳號 | 密碼 | 角色 |
|---|---|---|
| admin@cheerpsy.com | admin123 | 管理員 |
| accountant@cheerpsy.com | admin123 | 會計 |
| therapist1@cheerpsy.com | admin123 | 心理師 |

共 19 個預設帳號（1 管理員 + 1 會計 + 17 心理師）。
