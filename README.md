# CheerPsy 慈恩心理治療所管理系統

心理治療所的全端管理平台，包含對外預約網站與內部管理後台，兩套系統各自擁有獨立資料庫，確保財務與個案資料安全隔離。

## 系統組成

| 系統 | 用途 | 使用者 | Port |
|---|---|---|---|
| **Booking Portal** | 線上預約、瀏覽心理師 | 個案（一般民眾） | 3000 |
| **Admin Portal** | 排程、財務、報表、帳號管理 | 管理員 / 會計 / 心理師 | 3001 |

## 技術棧

- **Monorepo**: Turborepo + pnpm workspaces
- **Framework**: Next.js 14 (App Router, TypeScript)
- **Database**: PostgreSQL × 2 (Prisma ORM)
- **Auth**: NextAuth.js (Credentials + JWT)
- **UI**: Tailwind CSS + shadcn/ui
- **Charts**: Recharts
- **Excel**: ExcelJS
- **Validation**: Zod

## 專案結構

```
cheerpsy/
├── apps/
│   ├── admin/                # 內部管理系統
│   │   ├── prisma/           # Admin DB schema
│   │   ├── src/
│   │   └── railway.json
│   └── booking/              # 客戶預約系統
│       ├── prisma/           # Booking DB schema
│       ├── src/
│       └── railway.json
├── packages/
│   └── shared/               # 共用型別、Zod schemas、常數
├── services/
│   └── sync/                 # 跨資料庫同步邏輯
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

## 快速開始

### 前置需求

- Node.js >= 18
- pnpm >= 9
- PostgreSQL（本機或 Docker）

### 安裝

```bash
git clone https://github.com/iamleoluo/cheerpsy.git
cd cheerpsy
pnpm install
```

### 設定環境變數

複製 `.env.example` 並填入你的值：

```bash
cp apps/admin/.env.example apps/admin/.env
cp apps/booking/.env.example apps/booking/.env
```

需要的環境變數：

| 變數 | 說明 | 範例 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 連線字串 | `postgresql://user:pass@localhost:5432/cheerpsy_admin` |
| `NEXTAUTH_SECRET` | JWT 加密金鑰 | `openssl rand -base64 32` |
| `NEXTAUTH_URL` | 應用程式 URL | `http://localhost:3001` |
| `INTERNAL_API_SECRET` | 跨系統 API 共享密鑰 | `openssl rand -hex 48` |

### 初始化資料庫

```bash
# 建立 migration 並套用
cd apps/admin && npx prisma migrate dev --name init
cd ../booking && npx prisma migrate dev --name init

# 種子資料（管理員帳號 + 心理師帳號）
cd ../admin && npx tsx prisma/seed.ts && npx tsx prisma/seed-therapists.ts
```

### 啟動

```bash
# 同時啟動兩個系統
pnpm dev

# 或個別啟動
pnpm dev:admin    # http://localhost:3001
pnpm dev:booking  # http://localhost:3000
```

## 資料流

```
                    ┌──────────────┐
                    │  Excel 月報表  │
                    └──────┬───────┘
                           │ 匯入
                           ▼
┌──────────────┐    ┌──────────────┐
│  Booking     │    │  Admin       │
│  (預約資料庫)  │    │  (內部資料庫)  │
│              │    │              │
│  個案帳號     │    │  人員帳號     │
│  心理師公開資料 │◄───│  心理師主檔   │  ← 同步公開資料
│  預約紀錄     │───►│  諮商紀錄     │  ← 核准預約 → 建立紀錄
│              │    │  財務收支     │
└──────────────┘    └──────────────┘
```

- **心理師同步**：管理員從 Admin 將心理師公開資料推送到 Booking DB
- **預約核准**：個案預約 → 管理員/心理師核准 → 自動在 Admin DB 建立諮商紀錄
- **Excel 匯入**：上傳月報表 → 解析 22 欄 → 批次寫入 Admin DB

## 角色權限

| 功能 | 管理員 | 會計 | 心理師 |
|---|:---:|:---:|:---:|
| 預約管理 | 全部 | - | 僅自己 |
| 排程表 | 完整 | 唯讀 | 僅自己 |
| 新增/編輯諮商紀錄 | ✓ | - | - |
| 收款管理 | ✓ | ✓ | - |
| 報表（薪資/收入/分析） | ✓ | ✓ | - |
| 心理師管理 | ✓ | - | - |
| Excel 匯入 | ✓ | - | - |
| 帳號管理 | ✓ | - | - |
| CSV 匯出 | ✓ | ✓ | - |

## 測試帳號

### Admin Portal (localhost:3001)

| 角色 | Email | 密碼 |
|---|---|---|
| 管理員 | admin@cheerpsy.com | admin123 |
| 會計 | accountant@cheerpsy.com | demo1234 |
| 心理師 (17位) | `{pinyin}@cheerpsy.com` | demo1234 |

心理師帳號範例：`qiusiling@cheerpsy.com`、`liuyanjun@cheerpsy.com`

### Booking Portal (localhost:3000)

在 `/register` 自行註冊。

## 部署 (Railway)

專案已預設 Railway 部署設定：

1. 在 Railway 建立專案，連接 GitHub repo
2. 建兩個 service（Root Directory 分別指向 `apps/admin`、`apps/booking`）
3. 建兩個 PostgreSQL 實例
4. 設定環境變數（`DATABASE_URL`、`NEXTAUTH_SECRET`、`INTERNAL_API_SECRET`）
5. Railway 會自動執行 build 和 pre-deploy migration

詳細部署指南見 [`railway_deploy_guide.md`](railway_deploy_guide.md)。

## 文件

- [`REPORT.md`](REPORT.md) — 完整系統架構與功能報告（技術版）
- [`THERAPIST_GUIDE.md`](THERAPIST_GUIDE.md) — 心理師使用說明（非技術版）
- [`railway_deploy_guide.md`](railway_deploy_guide.md) — Railway 部署技術手冊

## License

Private — 慈恩心理治療所內部使用
