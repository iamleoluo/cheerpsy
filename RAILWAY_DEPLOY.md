# CheerPsy Railway 部署說明書

## 架構概覽

Railway 上需要建立 **4 個 service**：

```
┌─────────────────────────────────────────────┐
│  Railway Project: cheerpsy                   │
│                                              │
│  ┌──────────┐  ┌──────────┐                 │
│  │ PostgreSQL│  │  Redis   │                 │
│  │  (plugin) │  │ (plugin) │                 │
│  └────┬─────┘  └────┬─────┘                 │
│       │              │                       │
│  ┌────┴──────────────┴─────┐                │
│  │      API Service        │                 │
│  │   FastAPI (Python 3.11) │                 │
│  │   apps/api/Dockerfile   │                 │
│  └────────────┬────────────┘                │
│               │ internal network             │
│  ┌────────────┴────────────┐                │
│  │      Web Service        │                 │
│  │   Next.js 14 (Node 18)  │                 │
│  │   apps/web/Dockerfile   │                 │
│  └─────────────────────────┘                │
└─────────────────────────────────────────────┘
```

---

## Step 1: 建立 Railway Project

1. 登入 https://railway.app
2. 點選 **New Project**
3. 選擇 **Empty Project**
4. 命名為 `cheerpsy`

---

## Step 2: 新增 PostgreSQL

1. 在 project 內點選 **+ New** → **Database** → **PostgreSQL**
2. 建立完成後，點進 PostgreSQL service
3. 到 **Variables** tab，記下 `DATABASE_URL`（格式：`postgresql://postgres:xxx@xxx.railway.internal:5432/railway`）

---

## Step 3: 新增 Redis

1. 點選 **+ New** → **Database** → **Redis**
2. 建立完成（目前系統尚未使用 Redis，但預留）

---

## Step 4: 部署 API Service

### 4.1 建立 Service

1. 點選 **+ New** → **GitHub Repo** → 選擇 `iamleoluo/cheerpsy`
2. Service 命名為 `api`

### 4.2 設定 Build

在 **Settings** tab：

| 設定項 | 值 |
|--------|-----|
| **Root Directory** | `apps/api` |
| **Builder** | Dockerfile |
| **Dockerfile Path** | `Dockerfile` |

### 4.3 設定環境變數

在 **Variables** tab 加入：

| 變數 | 值 | 說明 |
|------|-----|------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | 用 Railway 的 reference variable 自動連結 |
| `JWT_SECRET` | （隨機產生 64 字元） | `openssl rand -hex 32` |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_MINUTES` | `480` | 8 小時 |
| `CORS_ORIGINS` | Web service 的公開 URL | 例如 `https://cheerpsy-web.up.railway.app` |
| `ID_ENCRYPTION_KEY` | （隨機產生 64 字元） | `openssl rand -hex 32` |
| `PORT` | `8000` | Railway 會自動設定，但明確指定較安全 |

> **產生密鑰指令：**
> ```bash
> openssl rand -hex 32
> ```

### 4.4 設定 Networking

1. 在 **Settings** → **Networking** 區塊
2. **Public Networking**：點選 **Generate Domain**，會得到類似 `cheerpsy-api-production.up.railway.app` 的域名
3. **Private Networking**：記下內部域名，格式為 `api.railway.internal`

### 4.5 Health Check（選填）

- **Health Check Path**: `/health`
- **Timeout**: `30` 秒

---

## Step 5: 部署 Web Service

### 5.1 建立 Service

1. 點選 **+ New** → **GitHub Repo** → 選擇 `iamleoluo/cheerpsy`
2. Service 命名為 `web`

### 5.2 設定 Build

在 **Settings** tab：

| 設定項 | 值 |
|--------|-----|
| **Root Directory** | `apps/web` |
| **Builder** | Dockerfile |
| **Dockerfile Path** | `Dockerfile` |

### 5.3 設定環境變數

在 **Variables** tab 加入：

| 變數 | 值 | 說明 |
|------|-----|------|
| `NEXT_PUBLIC_API_URL` | API 的**公開** URL | 例如 `https://cheerpsy-api-production.up.railway.app`（瀏覽器端呼叫用） |
| `API_URL` | API 的**內部** URL | 例如 `http://api.railway.internal:8000`（server-side auth 用，走內網更快） |
| `NEXTAUTH_SECRET` | （隨機產生 64 字元） | `openssl rand -hex 32` |
| `NEXTAUTH_URL` | Web service 的公開 URL | 例如 `https://cheerpsy-web.up.railway.app` |
| `PORT` | `3000` | |

> **重要：** `NEXT_PUBLIC_API_URL` 是 build-time 變數，修改後需要 **redeploy** 才會生效。

### 5.4 設定 Networking

1. **Public Networking**：點選 **Generate Domain**
2. 這個 URL 就是使用者存取系統的入口

---

## Step 6: 更新 CORS（重要！）

API 部署完、Web 域名確定後，回到 **API service** 的 Variables：

```
CORS_ORIGINS = https://你的web域名.up.railway.app
```

如果有多個域名（例如自訂域名），用逗號分隔：
```
CORS_ORIGINS = https://cheerpsy-web.up.railway.app,https://app.cheerpsy.com
```

---

## Step 7: 初始化資料庫

API service 的 Dockerfile 啟動時會自動執行 `alembic upgrade head`，所以 migration 會自動跑。

### 手動執行種子資料（首次部署）

在 Railway 的 API service 頁面，打開 **Shell** tab，執行：

```bash
python seed.py
```

這會建立 19 個預設帳號（1 admin + 1 accountant + 17 therapists）和 13 個治療室。

---

## Step 8: 驗證部署

### 8.1 API 健康檢查

```bash
curl https://你的api域名.up.railway.app/health
# 預期回應: {"status": "ok"}
```

### 8.2 API 文件

瀏覽器打開：
```
https://你的api域名.up.railway.app/docs
```

應該看到 FastAPI Swagger UI。

### 8.3 前端登入

1. 瀏覽器打開 `https://你的web域名.up.railway.app`
2. 應自動導向登入頁
3. 使用帳號：
   - **管理者**：`admin@cheerpsy.com` / `admin123`
   - **會計**：`accountant@cheerpsy.com` / `staff123`
   - **心理師**：`t001@cheerpsy.com` ~ `t017@cheerpsy.com` / `therapist123`

---

## 環境變數速查表

### API Service

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
CORS_ORIGINS=https://<web-domain>.up.railway.app
ID_ENCRYPTION_KEY=<openssl rand -hex 32>
```

### Web Service

```env
NEXT_PUBLIC_API_URL=https://<api-domain>.up.railway.app
API_URL=http://api.railway.internal:8000
NEXTAUTH_SECRET=<openssl rand -hex 32>
NEXTAUTH_URL=https://<web-domain>.up.railway.app
```

---

## 自訂域名（選填）

1. 在 Railway service 的 **Settings** → **Networking** → **Custom Domain**
2. 輸入你的域名（例如 `app.cheerpsy.com`）
3. 到 DNS 供應商新增 CNAME 記錄指向 Railway 提供的目標
4. 更新相關環境變數（`CORS_ORIGINS`, `NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`）

---

## 常見問題

### Q: 部署後前端 API 呼叫失敗（CORS 錯誤）
**A:** 確認 API service 的 `CORS_ORIGINS` 包含 Web service 的完整 URL（含 https://）。

### Q: 登入後一直跳回登入頁
**A:** 檢查 `NEXTAUTH_URL` 和 `NEXTAUTH_SECRET` 是否正確設定。`API_URL` 要用內部網路地址讓 server-side 能連到 API。

### Q: Alembic migration 失敗
**A:** 到 API service 的 **Deploy Logs** 查看錯誤。通常是 `DATABASE_URL` 設定有誤。可在 Shell 手動執行 `alembic upgrade head` 排查。

### Q: 修改前端程式碼後 API URL 沒更新
**A:** `NEXT_PUBLIC_API_URL` 是 build-time 注入的。改值後需要 **Redeploy**（不是 Restart）。

### Q: 資料庫需要備份
**A:** 管理者每天從系統匯出 CSV（諮商流水帳、月報表），存到 Google Drive 做手動備份。Railway PostgreSQL 也有自動 snapshot（付費方案）。

---

## 部署順序 Checklist

- [ ] 1. 建立 Railway Project
- [ ] 2. 新增 PostgreSQL database
- [ ] 3. 新增 Redis database
- [ ] 4. 建立 API service（GitHub repo, root: `apps/api`）
- [ ] 5. 設定 API 環境變數（DATABASE_URL, JWT_SECRET, CORS_ORIGINS, ID_ENCRYPTION_KEY）
- [ ] 6. 設定 API public domain
- [ ] 7. 建立 Web service（GitHub repo, root: `apps/web`）
- [ ] 8. 設定 Web 環境變數（NEXT_PUBLIC_API_URL, API_URL, NEXTAUTH_SECRET, NEXTAUTH_URL）
- [ ] 9. 設定 Web public domain
- [ ] 10. 更新 API 的 CORS_ORIGINS 為 Web 的公開 URL
- [ ] 11. 等待兩個 service 部署完成
- [ ] 12. 在 API Shell 執行 `python seed.py`
- [ ] 13. 驗證：API /health、Swagger UI、前端登入
