# 完整技術部署手冊：Turborepo + Next.js 14 + Prisma → Railway Pro

## TL;DR
- **遷移路徑**：把 Prisma `provider` 改為 `postgresql`、刪除舊 `prisma/migrations` 目錄、用 `prisma migrate dev --name init` 重新生成、在 Railway 用 pre-deploy command 跑 `prisma migrate deploy`；同時把 `better-sqlite3` 跨庫直連改成 admin → booking 的 internal API call（用共用 `INTERNAL_API_SECRET` 在 Railway 私有網路 `*.railway.internal` 內傳輸）。
- **Railway 部署**：在同一個專案下建兩個 service（admin、booking）+ 兩個 PostgreSQL，每個 service 用 Root Directory 指向 `apps/admin`、`apps/booking`，並用 `railway.json`/`railway.toml` 設定 `pnpm --filter` 的 build/start command；備份用 Railway 原生 Volume Backups（資料庫 service 內建排程）作為主要方式，若需要異地備份再加掛 `railwayapp-templates/postgres-s3-backups` 模板搭配 Railway Cron 將 `pg_dump` 推到 Cloudflare R2。
- **安全與維運**：admin 用 Next.js `middleware.ts` 讀 `x-forwarded-for` 做 IP 白名單；`AUTH_SECRET` 用 `npx auth secret` 或 `openssl rand -base64 32` 產生；Railway 自動配發 Let's Encrypt 憑證；Railway 不提供原生 rate limiting（需用 Upstash Redis + `@upstash/ratelimit` 自建）；rollback 使用 Deployments 分頁的 ⋯ 選單，30 天內可一鍵 rollback。

---

## Key Findings

| 主題 | 關鍵結論 |
|---|---|
| Prisma provider 切換 | Prisma 不支援同一份 migration 在 SQLite 與 PostgreSQL 共用（會丟 P3014）；必須刪掉 `prisma/migrations/` 重建。 |
| 資料型別 | SQLite 的 `DateTime` 以 INT(ms) 存、PostgreSQL 為 `TIMESTAMP(3)`；SQLite 沒有原生 `Boolean`（INT 0/1）、沒有 `Json`（TEXT），切到 PG 後 Prisma 會自動用真正的型別。 |
| better-sqlite3 替換 | 跨 service 不應再共享檔案；改為 admin 透過 booking 暴露的 internal route（`booking.railway.internal:3000`）+ Bearer shared secret 呼叫。 |
| 建置工具 | Railway 已從 Nixpacks 轉為 **Railpack**（2025 預設），但兩者都原生支援 pnpm workspaces。 |
| Monorepo 部署 | 推薦在每個 app 目錄放 `railway.json`，並設 service 的 **Root Directory** + **Watch Paths**，避免一個 service 變更觸發整個 monorepo 重建。 |
| Native backups | 2024-11 起 Railway 提供 **原生 Volume Backups**，PostgreSQL service 內建每日/每週/每月排程，副本依排程保留。 |
| 異地備份 | 若需 Cloudflare R2 異地備份，使用 `railwayapp-templates/postgres-s3-backups` 模板 + `SINGLE_SHOT_MODE=true` 搭配 Railway Cron。 |
| HTTPS | Railway 自動為 `*.up.railway.app` 與 custom domain 簽發 Let's Encrypt 憑證；對 root/apex 域名需要 ALIAS 或 CNAME flattening（GoDaddy/Hostinger 不支援，需轉到 Cloudflare DNS）。 |
| Rate limiting | Railway 平台不提供 application-level rate limiting；需自建（推薦 `@upstash/ratelimit` + Upstash Redis）。 |

---

## Details

### 1. SQLite → PostgreSQL 遷移

#### 1.1 Prisma schema 修改

```prisma
// prisma/schema.prisma （兩個 app 都要改）
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"     // ← 從 "sqlite" 改成這個
  url      = env("DATABASE_URL")
}

model Booking {
  id        String   @id @default(cuid())
  isPaid    Boolean  @default(false)        // SQLite: INT 0/1 → PG: BOOLEAN
  startAt   DateTime                        // SQLite: INT ms → PG: TIMESTAMP(3)
  metadata  Json?                           // SQLite: TEXT → PG: JSONB
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

#### 1.2 SQLite 與 PostgreSQL 型別差異重點

| Prisma 型別 | SQLite 實體 | PostgreSQL 實體 | 注意事項 |
|---|---|---|---|
| `Boolean` | INTEGER (0/1) | BOOLEAN | 直接 SQL dump 過去會失敗，要透過 Prisma 序列化。 |
| `DateTime` | INTEGER（ms epoch）或 TEXT（ISO-8601） | TIMESTAMP(3) | SQLite 沒有真正的 datetime 型別；如果你曾用原生 `better-sqlite3` 寫過字串日期，可能不是 Prisma 期待的格式。 |
| `Json` | TEXT | JSONB | PG 的 JSONB 可索引；如果欄位之前存的是非合法 JSON 字串會在匯入時失敗。 |
| `String @id` (cuid) | TEXT | TEXT | 不變 |
| `Int @default(autoincrement())` | INTEGER PRIMARY KEY | SERIAL/IDENTITY | 自動序列起始值要記得手動修正 (`SELECT setval(...)`). |
| 大小寫敏感性 | 預設不敏感 | 預設敏感（識別字符串會 lower-case 除非加引號） | 可能影響 `WHERE name = 'X'` 的查詢結果。 |
| 外鍵約束 | 預設關閉 | 預設啟用 | 之前 SQLite 容忍的孤兒列，PG 會直接拒絕。 |

#### 1.3 完整遷移流程

**Step 1 — 在本機備份 SQLite 資料**
```bash
sqlite3 prisma/booking.db ".backup 'booking_backup.db'"
sqlite3 prisma/admin.db ".backup 'admin_backup.db'"
```

**Step 2 — 修改 schema 並清掉舊 migration**
```bash
# 兩個 app 都做：
rm -rf prisma/migrations
rm -f prisma/migration_lock.toml
# schema 的 provider 改為 postgresql
```

**Step 3 — 啟動本機 PostgreSQL（測試用）**
```bash
docker run --name pg-dev -e POSTGRES_PASSWORD=dev -p 5432:5432 -d postgres:16-alpine
# .env
echo 'DATABASE_URL="postgresql://postgres:dev@localhost:5432/booking_dev"' > .env
```

**Step 4 — 重建 migration（dev 環境）**
```bash
pnpm --filter booking exec prisma migrate dev --name init
pnpm --filter admin   exec prisma migrate dev --name init
```
這會在 `prisma/migrations/<timestamp>_init/migration.sql` 產生 PG 專用的 SQL。

**Step 5 — 把 SQLite 資料匯到 PostgreSQL**

最穩的方法是寫一個一次性 Node script，用 Prisma Client 同時連兩端：

```ts
// scripts/migrate-data.ts
import { PrismaClient as SqlitePrisma } from "../prisma-sqlite-client";
import { PrismaClient as PgPrisma } from "@prisma/client";

const src = new SqlitePrisma({ datasources: { db: { url: "file:./booking_backup.db" } } });
const dst = new PgPrisma();

async function main() {
  const users = await src.user.findMany();
  for (const u of users) await dst.user.create({ data: u });

  const bookings = await src.booking.findMany();
  // 注意 DateTime 欄位：Prisma 會自動把 SQLite 的 INT(ms) 轉成 Date 物件
  for (const b of bookings) await dst.booking.create({ data: b });
}
main().finally(() => Promise.all([src.$disconnect(), dst.$disconnect()]));
```

替代方案：用 `pgloader`（指令更簡單但對 Prisma 的 `_prisma_migrations` 表會有額外處理）：
```bash
pgloader sqlite:///prisma/booking.db postgresql://user:pass@host/booking
# 之後執行 prisma migrate resolve 把 init migration 標為已套用：
pnpm prisma migrate resolve --applied <timestamp>_init
```

**Step 6 — 在 Railway 套用 migration（production）**

不要用 `migrate dev` 在 production 跑（會問你是否 reset DB）。改用 `migrate deploy`，並把它放進 Railway 的 **pre-deploy command**：

```jsonc
// apps/booking/railway.json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "RAILPACK",
    "buildCommand": "pnpm install --frozen-lockfile && pnpm --filter booking exec prisma generate && pnpm --filter booking build"
  },
  "deploy": {
    "preDeployCommand": "pnpm --filter booking exec prisma migrate deploy",
    "startCommand": "pnpm --filter booking start",
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

> 為什麼 pre-deploy 而不是 build：private network（Railway 內部 DNS 與 IPv6）在 build 階段不可用，只能在 runtime 連 PG。Railway 官方明確建議把 migration 放在 pre-deploy 而不是 build。

#### 1.4 常見錯誤

| 錯誤 | 原因 | 解法 |
|---|---|---|
| `P3014 The datasource provider postgresql does not match … sqlite` | `migration_lock.toml` 還記得 sqlite | 刪掉整個 `prisma/migrations` 重新 `migrate dev` |
| `P3009 migrate found failed migrations` | 之前一次失敗的 migration 卡住 | `prisma migrate resolve --rolled-back <name>` 或 `--applied` |
| `Can't reach database server` (build 時) | Railway private network 在 build 階段不可用 | 把 migration 移到 pre-deploy |
| `prisma: command not found` 在 production | `prisma` 在 devDependencies 被 prune | 把 `prisma` 移到 `dependencies` |
| 自動序列從 1 開始（資料匯入後新增主鍵衝突） | 沒有 reset PG sequence | `SELECT setval('"User_id_seq"', (SELECT MAX(id) FROM "User"));` |

**官方文件**：
- Prisma migrate 入門：https://www.prisma.io/docs/orm/prisma-migrate/getting-started
- Limitations & 切換 provider：https://www.prisma.io/docs/orm/prisma-migrate/understanding-prisma-migrate/limitations-and-known-issues
- Deploy database changes：https://www.prisma.io/docs/orm/prisma-client/deployment/deploy-database-changes-with-prisma-migrate

---

### 2. better-sqlite3 跨庫直連 → Internal API

#### 2.1 為什麼必須換掉

在 Railway 上每個 service 的 filesystem 是隔離的，admin 不可能再透過 `new Database('booking.db')` 直接讀 booking 的 SQLite 檔；即使用 PG 也不應該讓兩個 app 共用同一個資料庫實例（破壞服務邊界）。改成 **booking 暴露 internal API、admin 呼叫之**。

#### 2.2 架構設計

```
┌────────────────┐  HTTPS (公網)             ┌─────────────────┐
│  admin (3001)  │ ────────────────────────► │ Railway Edge    │
│                │                           └─────────────────┘
│  跨庫操作:     │
│   server      ─┼──► booking.railway.internal:3000/api/internal/*
│   action      │     ↑ 私有網路 IPv6, header: x-internal-secret
└────────────────┘
                                       ┌────────────────┐
                                       │ booking (3000) │
                                       │  /api/internal │  ← 驗證 shared secret
                                       │   /sync        │
                                       │   /bookings    │
                                       └────────────────┘
```

每個 service 都會自動取得 `<service-name>.railway.internal` 的 IPv6 內部 DNS（2025 年 10 月後的 environment 也支援 IPv4 內部解析）。

#### 2.3 實作 — booking 端（被呼叫者）

```ts
// apps/booking/app/api/internal/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { timingSafeEqual } from "crypto";

function verifySecret(req: NextRequest): boolean {
  const expected = process.env.INTERNAL_API_SECRET;
  if (!expected) return false;
  const got = req.headers.get("x-internal-secret") ?? "";
  if (got.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
}

export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  if (!verifySecret(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const [resource, action] = params.path;
  const body = await req.json();

  switch (`${resource}/${action}`) {
    case "bookings/upsert":
      return NextResponse.json(
        await prisma.booking.upsert({
          where: { id: body.id },
          update: body,
          create: body,
        }),
      );

    case "bookings/find":
      return NextResponse.json(
        await prisma.booking.findMany({ where: body.where, take: body.take ?? 50 }),
      );

    default:
      return NextResponse.json({ error: "unknown action" }, { status: 404 });
  }
}
```

對應的 Next.js 設定要把這個路徑強制 dynamic + Node runtime（因為要用 Prisma）：
```ts
// 同檔案頂部
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
```

#### 2.4 實作 — admin 端（呼叫者）

```ts
// apps/admin/lib/booking-client.ts
const BASE =
  process.env.NODE_ENV === "production"
    ? `http://booking.railway.internal:3000`         // Railway 內部，免費 egress
    : `http://localhost:3000`;

async function call<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api/internal/${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-internal-secret": process.env.INTERNAL_API_SECRET!,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`booking API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const bookingClient = {
  upsertBooking: (data: BookingInput) => call("bookings/upsert", data),
  listBookings:  (where: any, take?: number) => call("bookings/find", { where, take }),
};
```

> **重要**：Railway private network 預設只走 IPv6。Node ≥ 18 fetch 會優先試 IPv6 → IPv4 fallback，所以 OK；但若用某些 HTTP client（例如 axios + agentkeepalive 沒設 family=0），要明確允許 IPv6。詳見 https://docs.railway.com/reference/private-networking#how-the-private-network-works。

#### 2.5 環境變數配置

把 `INTERNAL_API_SECRET` 設成 Railway 的 **Shared Variable**，兩個 service 都自動引用：

```
# 工作區 → Project Settings → Shared Variables
INTERNAL_API_SECRET = <openssl rand -hex 48 產生>

# admin service Variables
INTERNAL_API_SECRET = ${{shared.INTERNAL_API_SECRET}}

# booking service Variables  
INTERNAL_API_SECRET = ${{shared.INTERNAL_API_SECRET}}
```

產生 secret：
```bash
openssl rand -hex 48
# 或
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

---

### 3. Railway 平台部署

#### 3.1 Railway Pro 帳號

- 訂閱費 $20/月，內含 $20 usage credit；單一 service 可使用 32 vCPU / 32 GB RAM 上限。
- 從 Workspace Settings → Plans 升級。Pro 才支援多人協作、無限 environment、自助 volume 擴容（最大 1 TB）、48GB volume snapshot 排程。
- **官方定價**：https://railway.com/pricing
- **Plan 比較**：https://docs.railway.com/reference/pricing/plans

#### 3.2 Monorepo 兩個 service 設定

**目錄結構**（假設）：
```
my-booking/
├── apps/
│   ├── admin/
│   │   ├── next.config.js
│   │   ├── package.json   (name: "admin")
│   │   └── railway.json
│   └── booking/
│       ├── next.config.js
│       ├── package.json   (name: "booking")
│       └── railway.json
├── packages/
│   └── shared/            (Prisma schema 可以放這裡或各 app)
├── pnpm-workspace.yaml
├── turbo.json
└── package.json
```

**步驟**：

1. 在 Railway dashboard 建立 New Project → Deploy from GitHub repo。
2. Railway 會偵測 monorepo 並提示為每個 deployable package 建立一個 service（pnpm/npm/yarn/bun 都會偵測）。
3. 為每個 service 在 **Settings → Source** 設定 Root Directory：
   - admin service → Root Directory = `apps/admin`
   - booking service → Root Directory = `apps/booking`
4. 設 **Watch Paths**（避免 booking 改動觸發 admin 重建）：
   - admin → `/apps/admin/**`、`/packages/**`、`/pnpm-lock.yaml`
   - booking → `/apps/booking/**`、`/packages/**`、`/pnpm-lock.yaml`

#### 3.3 Build / Start command（推薦做法）

每個 app 放一份 `railway.json`：

```jsonc
// apps/admin/railway.json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "RAILPACK",
    "buildCommand": "cd ../.. && pnpm install --frozen-lockfile && pnpm --filter admin exec prisma generate && pnpm --filter admin build"
  },
  "deploy": {
    "preDeployCommand": "cd ../.. && pnpm --filter admin exec prisma migrate deploy",
    "startCommand": "cd ../.. && pnpm --filter admin start",
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

booking 同款，把 `admin` 換成 `booking`。

> **Nixpacks vs Railpack**：2025 年起 Railway 預設使用 **Railpack**（Nixpacks 已 deprecated 但仍可用）。Railpack 對 pnpm workspaces 有原生支援、會自動快取 `.next/cache`、且自動偵測 `packageManager` 欄位。在 Settings → Build 可切換。  
> 文件：https://railpack.com/languages/node/

#### 3.4 root `package.json` 提供 start scripts（必要）

每個 Next.js app 內 `package.json`：
```json
{
  "name": "admin",
  "scripts": {
    "build": "next build",
    "start": "next start -p ${PORT:-3001} -H 0.0.0.0"
  }
}
```

**重點**：
- 必須 listen 在 `0.0.0.0`（不要 localhost），否則 Railway 偵測不到 port、healthcheck 會失敗。
- 必須讀 `process.env.PORT`（Railway 會注入），不能寫死 3001。Railway 會自動把第一次 detect 到的 port 設為 target port。
- 所以 `next start -p ${PORT:-3001}` 是正確寫法（local dev 預設 3001、prod 由 Railway 給）。

#### 3.5 Next.js 14 standalone output（建議）

雖然不強制，但對 Railway 部署有幫助（image 從 ~1.3GB 減到 ~80MB）：

```js
// apps/admin/next.config.js
const path = require('path');
module.exports = {
  output: 'standalone',
  outputFileTracingRoot: path.join(__dirname, '../../'),  // monorepo root
};
```

但用 standalone 後 start command 要改：
```bash
node ../../apps/admin/.next/standalone/apps/admin/server.js
```
（path doubling 是 monorepo + standalone 的已知行為）。如果懶，直接維持 `next start` 即可。

#### 3.6 PostgreSQL 建立

在專案 canvas 上 + New → Database → PostgreSQL，做兩次（一個給 admin、一個給 booking）。每個 PG service 會自動暴露：
- `DATABASE_URL`（內部 + private network）
- `DATABASE_PUBLIC_URL`（外部 TCP proxy）
- `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE`

在 admin / booking service 的 Variables tab 用 reference variable：
```
DATABASE_URL = ${{Postgres-Admin.DATABASE_URL}}
DATABASE_URL = ${{Postgres-Booking.DATABASE_URL}}
```
> 用 reference variable 而不是把字串貼進去：service 重啟、IP 變動會自動跟。

**重要**：一定要連 `DATABASE_URL`（私有網路、egress 免費）而不是 `DATABASE_PUBLIC_URL`（走外部 proxy、要計 egress 費用）。

#### 3.7 必要環境變數整理

每個 Next.js service：
```
# 認證
NEXTAUTH_SECRET = <openssl rand -base64 32>
NEXTAUTH_URL    = https://admin.example.com         # admin
NEXTAUTH_URL    = https://booking.example.com       # booking

# 資料庫
DATABASE_URL    = ${{Postgres-Admin.DATABASE_URL}}

# 內部 API 共享密鑰
INTERNAL_API_SECRET = ${{shared.INTERNAL_API_SECRET}}

# Admin 專用：IP 白名單（逗號分隔）
ADMIN_IP_ALLOWLIST = 1.2.3.4,5.6.7.8

# Node 環境
NODE_ENV = production
```

#### 3.8 Custom Domain

1. 在 service → Settings → Networking → + Custom Domain。
2. 輸入域名（例如 `admin.example.com`），Railway 會給你**兩筆 DNS 記錄**：
   - 一筆 CNAME（指到 `xxx.up.railway.app`）
   - 一筆 TXT（用於驗證所有權）
3. 兩筆都加到 DNS 提供商；TXT **沒加會 404**。
4. 等 DNS 傳遞後 Railway 自動申請 Let's Encrypt 憑證、自動續期（HTTPS 由 Railway 處理，無須額外設定）。
5. 若用 Cloudflare：把 `_acme-challenge` 那筆 TXT 的 proxy 關掉（橘雲變灰雲），否則驗證會失敗。
6. Apex domain（example.com 而非 admin.example.com）：需要 ALIAS 或 CNAME flattening。GoDaddy/Hostinger 不支援，建議把 DNS 移到 Cloudflare。

文件：https://docs.railway.com/networking/domains/working-with-domains

---

### 4. 備份方案

#### 4.1 Railway native backup（首選）

2024-11 起 Railway 提供原生 Volume Backups。PostgreSQL service 是用 volume 存資料，所以可以直接在 service 裡用：

1. PostgreSQL service → **Backups** tab。
2. 啟用排程：**Daily / Weekly / Monthly**（可同時開多個排程）。
3. 也可手動 **Take backup**。
4. 還原：點 backup 列上的 **Restore** → Railway 會把備份 mount 成新 volume、原 volume 保留 → 點 Deploy 完成切換。

特性：
- 增量 + Copy-on-Write，只算 backup 獨佔資料的 GB-min。
- 還原會把比這個還新的 backup 移除。
- backup 只能還原到同一個 project + environment。
- 手動 backup 上限是 volume 容量的 50%。

文件：https://docs.railway.com/volumes/backups

> 結論：**Railway 原生 backup 已可滿足大多需求**。但 backup 留在同一個 cloud provider 內部，若你要異地備援（disaster recovery），仍應加做下面的 R2 備份。

#### 4.2 Railway Cron + pg_dump → Cloudflare R2

**Step 1 — 在 Cloudflare 建 R2 bucket**
1. Cloudflare Dashboard → R2 → Create bucket → 名稱例如 `booking-backups`。
2. R2 → Manage R2 API Tokens → Create API Token → 權限 `Object Read & Write` → 限制到該 bucket。
3. 拿到 `Access Key ID`、`Secret Access Key`、`Account ID`；R2 endpoint = `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`。

**Step 2 — 在 Railway 部署官方備份模板**

直接點：https://railway.com/deploy/postgres-s3-backup-1（Railway 官方 template repo: https://github.com/railwayapp-templates/postgres-s3-backups）。

**Step 3 — 環境變數**
```
BACKUP_DATABASE_URL    = ${{Postgres-Booking.DATABASE_URL}}
AWS_ACCESS_KEY_ID      = <R2 access key>
AWS_SECRET_ACCESS_KEY  = <R2 secret>
AWS_S3_BUCKET          = booking-backups
AWS_S3_REGION          = auto
AWS_S3_ENDPOINT        = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_S3_FORCE_PATH_STYLE= false
SINGLE_SHOT_MODE       = true                     # 跑完就退出，配合 Railway Cron
BACKUP_FILE_PREFIX     = booking-prod-
BUCKET_SUBFOLDER       = booking/
PG_VERSION             = 16                       # 跟你 PG 版本一致
BACKUP_OPTIONS         = --no-owner --no-acl
```

**Step 4 — 設定 Railway Cron Schedule**

Service → Settings → **Cron Schedule**：
```
0 18 * * *
```
（每天 UTC 18:00 = 台灣時間 02:00 凌晨）

> 注意：Railway cron 的最小間隔是 **5 分鐘**、評估時區是 **UTC**、若上次執行還在跑會 **跳過下一次**（所以一定要 `SINGLE_SHOT_MODE=true` 讓進程完成後退出）。文件：https://docs.railway.com/cron-jobs。

**Step 5 — 為 admin DB 再開一個 backup service**（重複 step 2-4，把 `BACKUP_DATABASE_URL` 換成 admin 那條）。

#### 4.3 還原流程（從 R2）

```bash
# 本機或開一個臨時 Railway service
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=auto
export ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com

# 1. 列出可用的 backup
aws s3 ls s3://booking-backups/booking/ --endpoint-url $ENDPOINT

# 2. 下載
aws s3 cp s3://booking-backups/booking/booking-prod-2026-05-04T18-00.tar.gz . \
  --endpoint-url $ENDPOINT

# 3. 解壓
tar -xzvf booking-prod-2026-05-04T18-00.tar.gz

# 4. 還原（小心：會覆蓋 target）
psql "${DATABASE_URL}" -f dump.sql
# 或 pg_restore（取決於 dump format）：
pg_restore --clean --if-exists --no-owner -d "${DATABASE_URL}" dump.dump
```

> 在 production restore 前，先還原到一個 staging DB 驗證一次再切換 `DATABASE_URL`，避免覆蓋線上。

#### 4.4 備份策略建議

| 備份層級 | 工具 | 頻率 | 保留期 |
|---|---|---|---|
| 同 region 即時 | Railway native volume backup | 每日 | 7 天 |
| 異地 | Railway Cron + pg_dump → Cloudflare R2 | 每日 02:00 | 30 天（在 R2 設 lifecycle rule） |
| 重大發版前 | 手動 `pg_dump` 到本機 | ad-hoc | — |

R2 的 lifecycle rule：bucket Settings → Lifecycle → Add rule → Delete objects older than 30 days、prefix `booking/`。

---

### 5. 安全性設定

#### 5.1 Admin IP 白名單（middleware）

```ts
// apps/admin/middleware.ts
import { NextRequest, NextResponse } from "next/server";

const ALLOWED = (process.env.ADMIN_IP_ALLOWLIST ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

function getClientIp(req: NextRequest): string {
  // Railway 把真實 IP 放在 x-forwarded-for（第一段）
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  return req.headers.get("x-real-ip") ?? "0.0.0.0";
}

export function middleware(req: NextRequest) {
  // 健康檢查放行（Railway 用 healthcheck.railway.app 做 healthcheck）
  if (req.nextUrl.pathname.startsWith("/api/health")) {
    return NextResponse.next();
  }
  // NextAuth callback 放行
  if (req.nextUrl.pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  if (ALLOWED.length === 0) {
    // 沒設白名單就放行（dev / staging）
    return NextResponse.next();
  }

  const ip = getClientIp(req);
  if (!ALLOWED.includes(ip)) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  return NextResponse.next();
}

export const config = {
  // 套用到所有非靜態資源路徑
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

> Next.js 14 的 `NextRequest` 已**移除** `request.ip` 屬性（v15 完全砍掉，14 是 Vercel-only），self-host 必須讀 `x-forwarded-for`。文件：https://nextjs.org/docs/app/api-reference/functions/next-request

> 進階：要支援 CIDR 範圍可以裝 `ip-range-check` package。

#### 5.2 NEXTAUTH_SECRET（AUTH_SECRET）

NextAuth.js 在 production 強制要設 `NEXTAUTH_SECRET`（v5 別名為 `AUTH_SECRET`），用於加密 JWT。

```bash
# 推薦方式 1：用官方 CLI
npx auth secret
# 會自動寫入 .env.local

# 方式 2：openssl
openssl rand -base64 32
# Output: ph+5JZ4fZ/QkM...

# 方式 3（Windows）：
# https://generate-secret.vercel.app/32
```

把產出貼到 Railway Shared Variable：
```
NEXTAUTH_SECRET = <生成的字串>
AUTH_SECRET     = ${{shared.NEXTAUTH_SECRET}}   # v5 也讀這個
```
> **重要**：兩個 Next.js app（admin、booking）若各自有獨立使用者體系，**應該用不同的 secret**；若是 SSO 共用，才用同一個。

文件：
- NextAuth options：https://next-auth.js.org/configuration/options
- Auth.js deployment：https://authjs.dev/getting-started/deployment

#### 5.3 API Route shared secret（已在 §2.3 涵蓋）

要點：
1. 用 `crypto.timingSafeEqual` 而不是 `===` 比較（防 timing attack）。
2. Secret 至少 32 bytes 隨機（`openssl rand -hex 48`）。
3. **絕對不要**把 secret 印到 log；NextAuth/Prisma 都會自動擦，你的 console.log 不會。
4. 旋轉策略：每 90 天透過 Railway Shared Variable 換一次，兩 service 同時生效。

#### 5.4 HTTPS

Railway 自動處理：
- `*.up.railway.app`：直接是 HTTPS。
- Custom domain：CNAME + TXT 都加好後，Railway 自動向 Let's Encrypt 申請、自動續期（每 60-90 天）。
- 確認方式：`curl -vI https://admin.example.com 2>&1 | grep -i 'subject:\|issuer:'` 應看到 Let's Encrypt 為 issuer。

對 Next.js 端額外建議：在 production 強制安全 cookie：
```ts
// app/api/auth/[...nextauth]/route.ts
export const authOptions: AuthOptions = {
  // ...
  cookies: {
    sessionToken: {
      name: process.env.NODE_ENV === "production"
        ? "__Secure-next-auth.session-token"
        : "next-auth.session-token",
      options: {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        secure: process.env.NODE_ENV === "production",
      },
    },
  },
};
```

#### 5.5 Rate limiting 現況確認

**Railway 不提供 application-level rate limiting**（平台只有 logging rate limit：500 lines/sec/replica，超過會 drop log）。要對 API 做限速必須自建。

**推薦方案：Upstash Redis + `@upstash/ratelimit`**

1. 在 Railway 點 + New → Database → 從 template 找 **Redis**（或用 Upstash 的免費 tier）。
2. 在 Next.js 安裝：
   ```bash
   pnpm add @upstash/ratelimit @upstash/redis
   ```
3. `apps/admin/lib/ratelimit.ts`：
   ```ts
   import { Ratelimit } from "@upstash/ratelimit";
   import { Redis } from "@upstash/redis";

   export const ratelimit = new Ratelimit({
     redis: Redis.fromEnv(),
     limiter: Ratelimit.slidingWindow(20, "10 s"),  // 每 IP 10 秒 20 次
     analytics: true,
     prefix: "rl:admin",
   });
   ```
4. 在 middleware 或 API route 套用：
   ```ts
   const ip = getClientIp(req);
   const { success, limit, remaining, reset } = await ratelimit.limit(ip);
   if (!success) {
     return new NextResponse("Too Many Requests", {
       status: 429,
       headers: {
         "X-RateLimit-Limit": String(limit),
         "X-RateLimit-Remaining": String(remaining),
         "X-RateLimit-Reset": String(reset),
       },
     });
   }
   ```

> 邊際選項：對 **NextAuth 登入端點**特別限速（防暴力破解），可在 `/api/auth/callback/credentials` 用更嚴格的窗口（5 次/分鐘/IP）。

文件：
- Upstash ratelimit：https://github.com/upstash/ratelimit-js
- Upstash 官方教學：https://upstash.com/blog/nextjs-ratelimiting

---

### 6. 上線後維運

#### 6.1 Logs

**從 Dashboard 看**：
- Service → **Deployments** tab → 點某個 deployment → **Build logs / Deploy logs**。
- Project 頂部 → **Observability** → Logs widget（跨 service 搜尋）。

**從 CLI 看**（推薦在開發機常駐）：
```bash
# 安裝
brew install railway     # macOS
# 或
npm i -g @railway/cli

railway login
railway link             # 連到 project
railway logs --service admin
railway logs --service booking --deployment   # 只看當前 active deployment
```

**Log Explorer 進階查詢**：
```
@level:error                            # 只看 error
@level:error service:admin              # 限定 service
"booking" -"healthcheck"                # 包含 booking 但排除 healthcheck
@srcIp:1.2.3.4                         # HTTP log：依來源 IP 篩
```

**結構化 log**（強烈建議）：
```ts
// 用 pino 或 winston，輸出 JSON
import pino from "pino";
export const logger = pino({ level: process.env.LOG_LEVEL ?? "info" });

logger.info({ userId, route: "/api/booking" }, "booking created");
// → Railway 自動 parse JSON、提供 @userId 等 attribute 篩選
```

> 注意：Railway 對每個 replica 有 **500 log lines/sec** 上限，超過 drop。high-volume app 要避免 pretty-print、過度 debug log。

文件：https://docs.railway.com/observability/logs

#### 6.2 Rollback 與 Redeploy

**Rollback（一鍵回到前一版）**：
1. Service → **Deployments** tab。
2. 找到一個之前 SUCCESS 的 deployment → 右側 ⋯ 選單 → **Rollback**。
3. 確認 → Railway 會立即把流量切回那個 image + 那次的環境變數。

**注意**：
- 只有 `canRollback: true` 的 deployment 可以 rollback。
- Pro plan 預設保留近期 deployment 約 **30 天**，超過就只能 **Redeploy**（從原 source code rebuild）。
- Rollback **同時還原 Docker image 與當時的環境變數**，所以如果你 rollback 之後又改了環境變數，記得它是依當時值跑。

**Redeploy（重跑當前 source）**：
```bash
railway redeploy --service admin
```
或 Dashboard 的 ⋯ → Redeploy。

**從 GraphQL API 自動化**：https://docs.railway.com/integrations/api/manage-deployments

#### 6.3 監控資源用量

**Service-level metrics**（每個 service 內建）：
- Service → **Metrics** tab → CPU / Memory / Disk / Network in-out（30 天歷史）。
- 多 replica 可選 sum 或 per-replica 顯示。

**Project-level Observability Dashboard**：
- Project 頂部 → **Observability** → **Start with a simple dashboard**。
- 自動產生 spend、CPU、memory、log widgets。
- 可加 widgets：Project Usage（這個 billing cycle 的花費）、Logs（自訂 filter）。

**Alerts（Monitors）**：
- 任何 Observability widget → ⋯ → **Add Monitor**。
- 設定 e.g.「CPU > 80% 持續 5 分鐘」→ 透過 email 通知。
- Webhook：Project Settings → Webhooks → 加入 Slack / Discord webhook URL，可收到 deploy succeeded / crashed 等事件。

**Workspace usage**（看花費）：
- Workspace Settings → **Usage** → 依 project / service / 資源類型（CPU/Memory/Network/Disk）拆分。
- Alert：設 spending limit，超過自動暫停 service（避免帳單失控）。

**第三方工具（要留更久 log / APM）**：
- 用 OpenTelemetry SDK + 任何 OTLP 後端（Datadog / Honeycomb / Grafana Cloud / SigNoz）。
- Railway 沒有 log drain，需自架 Vector / Fluent Bit 作為 forwarder。
- 文件：https://docs.railway.com/guides/third-party-observability

#### 6.4 部署失敗排查清單

| 症狀 | 可能原因 | 解法 |
|---|---|---|
| Build 失敗：`No projects matched the filters` | pnpm-workspace.yaml 沒在 root、或 root directory 設錯 | 確認 root directory = `apps/<name>`、且 buildCommand 用 `cd ../..` 跳到 monorepo root |
| Healthcheck timeout | App 沒 listen 在 `0.0.0.0:$PORT`、或 startup 真的太慢 | 確認 `next start -p $PORT -H 0.0.0.0`；增加 `RAILWAY_HEALTHCHECK_TIMEOUT_SEC`（最大 999）；確認 `/api/health` 回 200 |
| Healthcheck 403 | Middleware 把 `healthcheck.railway.app` 擋掉 | middleware 對 `/api/health` 提前 return（如 §5.1 範例） |
| `Can't reach database server` | 在 build 階段試圖連 DB，或用了 public URL | migration 移到 pre-deploy；環境變數用 `DATABASE_URL`（private）不是 `DATABASE_PUBLIC_URL` |
| Image 太大 / build 慢 | 沒用 standalone、node_modules 進到 image | 啟用 `output: "standalone"` + `outputFileTracingRoot` |
| 內部 fetch 失敗 (`ENOTFOUND booking.railway.internal`) | private network 在 build 階段不可用、或 client 不支援 IPv6 | 只在 runtime fetch；確認 Node ≥ 18 |
| Crashed: `prisma: command not found` | prune 掉 devDependencies | 把 `prisma` 移到 `dependencies` |
| Custom domain 404 | TXT record 沒加 | 補上 Railway 給的 TXT record |
| Cron 沒跑 | 上次 process 沒 exit | 確認跑完 `process.exit(0)`、`SINGLE_SHOT_MODE=true` |

文件：https://docs.railway.com/deployments/troubleshooting/slow-deployments

---

## Caveats

1. **Railway Pro 不是固定費**：$20/月 base 後超出 credit 是按用量 billing（per-second per-resource）。Idle 的 staging service 不關仍會計費；建議 staging environment 啟用 **app sleeping**（service Settings 中），或乾脆用 `railway down` 暫停。

2. **Prisma 7 支援度**：本手冊範例以 Prisma 6.x 假設（`prisma-client-js` generator + 標準 `DATABASE_URL`）。Prisma 7 改用 `prisma-client` generator + `prisma.config.ts` + driver adapter（`@prisma/adapter-pg`），整體 API 相容但部署 script 略不同。如果你還在 6.x 不需要急著升。

3. **`output: "standalone"` 在 monorepo + Turbopack** 在 2025 年仍有 path doubling 已知 bug（Next.js issue #88579），如果 standalone build 找不到 server.js，先用標準 `next start` 部署，等 Next.js 修好再開 standalone。

4. **Railway native backup 限制**：只能在「同一個 project + environment」內還原；要跨環境或跨帳號搬，仍須 pg_dump。它**不是** point-in-time recovery（PITR），只是定時 snapshot；對於需要 RPO < 24h 的場景考慮 Neon / Supabase 等具備 PITR 的服務。

5. **中文文件**：本手冊引用的所有官方文件目前皆為英文，連結均為英文版。Prisma 與 Railway 的繁體中文社群文件不齊全，遇到問題建議直接查英文 docs + Discord（Railway Discord、Prisma Discord 都很活躍）。

6. **Edge runtime 限制**：Next.js middleware 預設跑在 Edge runtime，**不能用 Prisma**（除非 driver adapter）也不能用 Node-only API。本文 IP allowlist middleware 只用 `headers.get`，Edge OK；如果你想在 middleware 直接查 DB 做動態白名單，必須加 `export const runtime = "nodejs"`（Next.js 13.4+ 才支援 Node middleware，且效能較差）。

7. **`request.ip` 已不可用**：本手冊一律使用 `x-forwarded-for`。如果你網路上看到舊範例用 `request.ip`，那是 Vercel-only API，self-host 不會有值。

8. **Railway 的 IP 並非靜態**：service egress IP 會變動。如果你呼叫的第三方 API 需要 IP 白名單，Pro 以上才能買 **Static Outbound IP** add-on（文件：https://docs.railway.com/networking/static-outbound-ips）。

9. **Cron 時區為 UTC**：所有 schedule 用 UTC。台灣 UTC+8 換算注意：每天台灣時間 02:00 = UTC 18:00 前一天。

10. **Healthcheck timeout 上限 999 秒**：超長啟動的 app（如 indexer）目前無法解決，須拆出獨立的「初始化 worker」service。本手冊的 Next.js 場景不會碰到。