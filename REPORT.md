# 慈恩心理治療所管理系統 — 系統架構與功能報告

## 一、系統概覽

本系統為「慈恩心理治療所」設計的全端管理平台，分為兩套完全獨立的系統：

1. **客戶預約系統（Booking Portal）** — 對外公開，供個案註冊、瀏覽心理師、線上預約
2. **內部管理系統（Admin Portal）** — 對內使用，供管理員、會計、心理師管理排程、財務、報表

兩套系統各自擁有獨立的資料庫，彼此資料隔離。當預約被管理員核准時，資料才會從預約資料庫「複製」到內部資料庫，確保即使預約系統被入侵，內部財務與個案資料不會外洩。

---

## 二、技術架構

### 2.1 專案結構

```
cheerpsy/
├── apps/
│   ├── admin/                 ← 內部管理系統（Next.js, port 3001）
│   │   └── prisma/
│   │       ├── schema.prisma  ← 內部資料庫結構定義
│   │       └── internal.db    ← SQLite 內部資料庫
│   └── booking/               ← 客戶預約系統（Next.js, port 3000）
│       └── prisma/
│           ├── schema.prisma  ← 預約資料庫結構定義
│           └── booking.db     ← SQLite 預約資料庫
├── packages/
│   └── shared/                ← 共用程式碼（型別、驗證規則、常數）
├── services/
│   └── sync/                  ← 跨資料庫同步邏輯
├── data/
│   └── backup/                ← 原始 Excel 備份
├── turbo.json                 ← Turborepo 設定
├── pnpm-workspace.yaml        ← pnpm 工作區設定
└── package.json
```

### 2.2 技術選型

| 項目 | 技術 |
|---|---|
| 框架 | Next.js 14（App Router, TypeScript） |
| 單體倉庫 | Turborepo + pnpm workspaces |
| 資料庫 | SQLite × 2（透過 Prisma ORM） |
| 認證 | NextAuth.js（Credentials Provider, JWT） |
| UI | Tailwind CSS + shadcn/ui 風格元件 |
| 圖表 | Recharts |
| Excel 讀寫 | ExcelJS |
| 跨資料庫存取 | better-sqlite3（Admin 直接讀寫 Booking DB） |
| 表單驗證 | Zod |
| 語言 | 全系統繁體中文介面 |

---

## 三、資料庫設計

### 3.1 內部資料庫（internal.db）

儲存所有敏感的營運資料，僅內部系統可存取。

| 資料表 | 說明 | 欄位數 |
|---|---|---|
| `staff_users` | 內部人員帳號 | email, 密碼, 姓名, 角色(admin/accountant/therapist), 關聯心理師 |
| `therapists` | 心理師主檔 | 姓名(唯一), 抽成比率, 是否啟用, 簡介, 專長 |
| `therapist_availability` | 心理師可用時段 | 星期幾, 開始/結束時間, 是否循環 |
| `clients` | 個案主檔 | 姓名, 電話, email, 備註, 關聯預約系統用戶ID |
| `sessions` | 諮商紀錄（核心） | 日期, 空間, 心理師, 個案, 收費形式, 應收/實收金額, 收款狀況, 諮商形式/種類, 時數, 鐘點, 抽成, 心理師/治療所收入, 給付狀態, 來源(excel_import/manual/booking) |
| `import_logs` | Excel匯入紀錄 | 檔名, 匯入筆數, 匯入者, 時間 |

### 3.2 預約資料庫（booking.db）

僅儲存公開預約相關資料，不含任何財務資訊。

| 資料表 | 說明 | 欄位數 |
|---|---|---|
| `client_users` | 客戶帳號 | email, 密碼, 姓名, 電話, 最後登入時間 |
| `therapist_profiles` | 心理師公開資料（從內部同步） | 姓名, 簡介, 專長, 是否接受預約, 內部心理師ID |
| `therapist_availability` | 可預約時段（從內部同步） | 星期幾, 開始/結束時間 |
| `appointments` | 預約紀錄 | 客戶, 心理師(可選), 日期, 時段, 形式(實體/視訊), 狀態(pending/confirmed/rejected/cancelled), 拒絕原因 |

---

## 四、資料流

### 4.1 系統間資料流向圖

```
┌──────────────────────────┐                    ┌──────────────────────────┐
│   客戶預約系統 (Booking)   │                    │   內部管理系統 (Admin)     │
│   http://localhost:3000   │                    │   http://localhost:3001   │
│                          │                    │                          │
│  ┌────────────────────┐  │   ② 核准預約        │  ┌────────────────────┐  │
│  │  預約資料庫          │  │ ──────────────→    │  │  內部資料庫          │  │
│  │  booking.db         │  │   建立諮商紀錄      │  │  internal.db        │  │
│  │                    │  │   更新預約狀態       │  │                    │  │
│  │  · 客戶帳號         │  │                    │  │  · 人員帳號          │  │
│  │  · 心理師公開資料    │  │   ① 同步心理師      │  │  · 心理師主檔        │  │
│  │  · 預約紀錄         │  │ ←──────────────    │  │  · 個案主檔          │  │
│  └────────────────────┘  │   公開資料同步       │  │  · 諮商紀錄          │  │
│                          │                    │  │  · 匯入紀錄          │  │
│  個案操作：              │                    │  └────────────────────┘  │
│  · 註冊/登入            │                    │                          │
│  · 瀏覽心理師           │                    │  ③ Excel 匯入             │
│  · 送出預約             │                    │  原始月報表 → 諮商紀錄      │
│  · 查看預約狀態          │                    │                          │
└──────────────────────────┘                    └──────────────────────────┘
```

### 4.2 三條主要資料流

#### 流程 ①：心理師資料同步（內部 → 預約）

```
管理員在 Admin 按「同步心理師至預約系統」
  → 讀取內部資料庫 therapists 表（姓名、簡介、專長）
  → 寫入預約資料庫 therapist_profiles 表
  → 預約系統首頁與心理師頁面即可顯示
```

#### 流程 ②：預約核准（預約 → 內部）

```
個案在 Booking 送出預約（status = pending）
  → 管理員/心理師在 Admin「預約管理」頁面看到待確認預約
  → 按「核准」並指定心理師
  → 系統自動：
    1. 在內部資料庫建立 client（個案）記錄
    2. 在內部資料庫建立 session（諮商紀錄），source = 'booking'
    3. 更新預約資料庫中該預約的 status = 'confirmed'
  → 個案在 Booking「我的預約」看到狀態變為「已確認」
```

#### 流程 ③：Excel 匯入

```
管理員在 Admin「Excel匯入」頁面上傳月報表
  → 系統解析 raw 工作表，對應 22 個欄位（B-V 欄）
  → 預覽顯示前 20 筆資料、心理師與個案數量
  → 確認後：
    1. Upsert 心理師到 therapists 表
    2. Upsert 個案到 clients 表
    3. 批次建立 sessions，source = 'excel_import'
    4. 記錄匯入日誌
  → 支援「新增」模式（保留現有）與「取代」模式（刪除舊匯入資料）
```

---

## 五、使用者角色與操作指南

### 5.1 角色權限總表

| 功能 | 管理員 (admin) | 會計 (accountant) | 心理師 (therapist) |
|---|:---:|:---:|:---:|
| 總覽儀表板 | ✅ | ✅ | ✅ |
| 預約管理（核准/拒絕） | ✅ | ❌ | ✅ 僅自己的 |
| 排程表 | ✅ 完整 | ✅ 唯讀 | ✅ 僅自己的 |
| 月曆檢視 | ✅ | ✅ 唯讀 | ✅ 僅自己的 |
| 新增/編輯諮商紀錄 | ✅ | ❌ | ❌ |
| 收款管理（已收/未收） | ✅ | ✅ | ❌ |
| 薪資核發報表 | ✅ | ✅ | ❌ |
| 治療所收入報表 | ✅ | ✅ | ❌ |
| 收費分析報表 | ✅ | ✅ | ❌ |
| 心理師管理 | ✅ | ❌ | ❌ |
| 個案管理 | ✅ | ❌ | ✅ 僅自己的 |
| Excel 匯入 | ✅ | ❌ | ❌ |
| 帳號管理 | ✅ | ❌ | ❌ |
| 同步心理師至預約系統 | ✅ | ❌ | ❌ |
| CSV 匯出 | ✅ | ✅ | ❌ |

### 5.2 管理員操作流程

1. **登入** → `admin@cheerpsy.com` / `admin123`
2. **匯入歷史資料** → 「Excel匯入」頁面上傳月報表
3. **建立帳號** → 「帳號管理」為心理師、會計建立帳號
4. **同步心理師** → 「預約管理」按「同步心理師至預約系統」
5. **管理預約** → 「預約管理」查看待確認預約，核准或拒絕
6. **查看報表** → 薪資核發、治療所收入、收費分析
7. **管理收款** → 「收款管理」批次標記已收/已付

### 5.3 會計操作流程

1. **登入** → `accountant@cheerpsy.com` / `demo1234`
2. **查看排程** → 「排程表」瀏覽所有諮商紀錄（唯讀）
3. **管理收款** → 「收款管理」篩選未收款/未付心理師，批次更新
4. **查看報表** → 三種報表皆可使用，支援日期範圍篩選與 CSV 匯出

### 5.4 心理師操作流程

1. **登入** → 例如 `qiusiling@cheerpsy.com` / `demo1234`
2. **查看排程** → 「我的排程」僅顯示自己的諮商紀錄
3. **管理預約** → 「我的預約」查看指定給自己的預約，可核准

### 5.5 個案（客戶端）操作流程

1. **註冊** → 在預約系統 `http://localhost:3000/register` 建立帳號
2. **瀏覽心理師** → 查看心理師簡介、專長、可預約時段
3. **送出預約** → 選擇心理師（可不指定）、日期、時段、實體/視訊
4. **追蹤狀態** → 「我的預約」查看待確認/已確認/已拒絕/已取消
5. **取消預約** → 待確認狀態下可自行取消

---

## 六、已完成功能清單

### 6.1 基礎建設
- [x] Turborepo + pnpm 工作區設定
- [x] 兩套 Next.js 14 應用程式
- [x] 兩套獨立 SQLite 資料庫（Prisma ORM）
- [x] 共用套件（types, schemas, constants）
- [x] Tailwind CSS + shadcn/ui 風格元件
- [x] 管理員/心理師/會計 種子資料（19 個帳號）

### 6.2 內部管理系統（Admin）
- [x] NextAuth 認證（JWT + Credentials）
- [x] 角色權限中介層（middleware）
- [x] 側邊欄導航（依角色顯示不同選單）
- [x] 響應式設計（手機版漢堡選單）
- [x] 儀表板（諮商紀錄數、心理師數、個案數）
- [x] Excel 匯入（預覽 + 確認、新增/取代模式）
- [x] 排程表（篩選、分頁）
- [x] 月曆檢視
- [x] 諮商紀錄新增/編輯/刪除
- [x] 自動計算（時數 × 鐘點 = 應收 → 心理師收入/治療所收入）
- [x] 收款管理（篩選未收/未付、批次更新）
- [x] 薪資核發報表（依心理師 × 收費形式彙總、稅 10%、二代健保 2.11%）
- [x] 治療所收入報表（KPI 卡片、長條圖、圓餅圖、趨勢圖）
- [x] 收費分析報表（自費 vs 機構、各收費形式明細、心理師分佈）
- [x] CSV 匯出（UTF-8 BOM，中文正常顯示）
- [x] 心理師 CRUD（姓名、抽成、簡介、專長、啟用/停用）
- [x] 個案列表（搜尋）
- [x] 帳號管理（新增/刪除、角色設定、關聯心理師）
- [x] 個人設定（變更密碼）
- [x] 預約管理（列出待確認預約、核准/拒絕）
- [x] 心理師資料同步至預約系統

### 6.3 客戶預約系統（Booking）
- [x] 首頁（治療所介紹、心理師卡片）
- [x] 客戶註冊/登入（NextAuth）
- [x] 心理師瀏覽頁（簡介、專長、可預約時段）
- [x] 預約表單（選心理師、日期、時段、實體/視訊）
- [x] 預約成功頁
- [x] 我的預約（狀態追蹤、取消功能）
- [x] 頻率限制（Rate Limiting）

### 6.4 跨系統同步
- [x] 心理師資料同步（Admin → Booking）
- [x] 預約核准流程（Booking → Admin，建立諮商紀錄）
- [x] 預約拒絕流程（含拒絕原因）

---

## 七、未完成 / 待優化項目

### 7.1 功能面

| 項目 | 優先級 | 說明 |
|---|---|---|
| 心理師時段管理 UI | 高 | Admin 目前缺少設定心理師可用時段的介面，需新增 therapist_availability CRUD 頁面 |
| 時段衝突檢查 | 高 | 預約時未檢查該時段是否已有其他預約或諮商 |
| Email 通知 | 高 | 預約確認/拒絕時應發送 email 通知個案 |
| 儀表板 KPI 強化 | 中 | 目前僅顯示三個數字，應加入本月營收、未收款金額、待確認預約數、圖表趨勢 |
| XLSX 匯出 | 中 | 目前僅支援 CSV 匯出，應加入 XLSX 格式（含格式化）以完整對應原始報表 |
| 機構核銷月份篩選 | 中 | 報表應支援依機構核銷月份篩選，而非僅依日期 |
| 個案詳細頁 | 中 | 點擊個案可查看該個案所有諮商歷史 |
| 心理師自己的收入報表 | 中 | 心理師登入後可查看自己的收入彙總 |
| 預約系統 — 心理師詳細頁 | 低 | 點擊心理師可查看完整介紹與評價 |
| 多月份 Excel 匯入 | 低 | 目前假設 raw sheet 為單月資料，應支援跨月匯入與月份標記 |
| 重複預約防止 | 低 | 同一個案同一時段不應重複預約 |

### 7.2 安全性

| 項目 | 優先級 | 說明 |
|---|---|---|
| CSRF 保護 | 高 | API routes 應加入 CSRF token 驗證 |
| 密碼重設功能 | 高 | 目前僅管理員可重設密碼，應提供自助重設 |
| Admin IP 白名單 | 中 | 生產環境應限制 Admin 系統的存取來源 IP |
| API Rate Limiting（Admin） | 中 | Admin API 目前無頻率限制 |
| 登入失敗鎖定 | 中 | 多次登入失敗應暫時鎖定帳號 |
| 敏感資料加密 | 低 | 個案姓名、電話等應考慮欄位加密 |

### 7.3 部署與維運

| 項目 | 優先級 | 說明 |
|---|---|---|
| 生產環境部署設定 | 高 | Dockerfile、環境變數管理、HTTPS |
| 資料庫備份機制 | 高 | SQLite 定期備份腳本 |
| 將 SQLite 改為 PostgreSQL | 中 | 多人同時寫入時 SQLite 有鎖定問題，生產環境建議改用 PostgreSQL |
| 日誌與監控 | 中 | 加入結構化日誌、錯誤監控（如 Sentry） |
| CI/CD 流程 | 低 | GitHub Actions 自動測試與部署 |
| 單元測試與 E2E 測試 | 低 | 目前無自動化測試 |

### 7.4 使用體驗

| 項目 | 優先級 | 說明 |
|---|---|---|
| 載入骨架屏 | 中 | 各頁面載入時應顯示 skeleton 而非純文字「載入中...」 |
| 表單驗證提示優化 | 中 | 目前部分表單的錯誤提示不夠友善 |
| 深色模式 | 低 | 支援深色主題切換 |
| 多語系支援 | 低 | 目前僅繁體中文，如有需求可加入英文 |

---

## 八、目前測試帳號一覽

### 內部管理系統（http://localhost:3001）

| 姓名 | Email | 密碼 | 角色 |
|---|---|---|---|
| 系統管理員 | admin@cheerpsy.com | admin123 | 管理員 |
| 會計人員 | accountant@cheerpsy.com | demo1234 | 會計 |
| 邱似齡 | qiusiling@cheerpsy.com | demo1234 | 心理師 |
| 邱惟雅 | qiuweiya@cheerpsy.com | demo1234 | 心理師 |
| 邱意祺 | qiuyiqi@cheerpsy.com | demo1234 | 心理師 |
| 劉彥君 | liuyanjun@cheerpsy.com | demo1234 | 心理師 |
| 劉柏宏 | liubohong@cheerpsy.com | demo1234 | 心理師 |
| 呂孟育 | lvmengyu@cheerpsy.com | demo1234 | 心理師 |
| 林容蒂 | linrongdi@cheerpsy.com | demo1234 | 心理師 |
| 林紀宇 | linjiyu@cheerpsy.com | demo1234 | 心理師 |
| 楊顯欽 | yangxianqin@cheerpsy.com | demo1234 | 心理師 |
| 游子瑩 | youziying@cheerpsy.com | demo1234 | 心理師 |
| 潘柔靜 | panroujing@cheerpsy.com | demo1234 | 心理師 |
| 羅紀萱 | luojixuan@cheerpsy.com | demo1234 | 心理師 |
| 葉邦彥 | yebangyan@cheerpsy.com | demo1234 | 心理師 |
| 蔡孟潔 | caimengjie@cheerpsy.com | demo1234 | 心理師 |
| 鄭幼毅 | zhengyouyi@cheerpsy.com | demo1234 | 心理師 |
| 陳慧苓 | chenhuiling@cheerpsy.com | demo1234 | 心理師 |
| 黃慧婷 | huanghuiting@cheerpsy.com | demo1234 | 心理師 |

### 客戶預約系統（http://localhost:3000）

自行在 `/register` 頁面註冊即可使用。

---

## 九、Excel 欄位對應表

原始檔案：`慈恩會計行政月報表日更格式1150503.xlsx`，工作表 `raw`

| Excel 欄 | 欄位名稱 | 資料庫對應欄位 | 說明 |
|---|---|---|---|
| A | （空白） | — | 忽略 |
| B | date | session.date | 日期 |
| C | 空間 | session.room | 例：3D |
| D | 心理師 | therapist.name → FK | 自動建立心理師 |
| E | 收費形式 | session.billing_type | 自費/家防/台積/青壯... |
| F | 應收金額 | session.amount_receivable | 向個案收取的金額 |
| G | 應收類型 | session.receivable_type | 匯款/現金收取/機構申請 |
| H | 諮商地點 | session.location | 治療所/外訪到宅 |
| I | 收款狀況 | session.payment_status | 已收/未收 |
| J | 當日實收金額 | session.amount_received | 當日實際收到的金額 |
| K | 機構核銷月份 | session.institution_month | 機構核銷的月份 |
| L | 個案姓名 | client.name → FK | 自動建立個案 |
| M | 諮商形式 | session.counseling_format | 實體/視訊 |
| N | 諮商種類 | session.counseling_type | 個別 |
| O | 時數 | session.hours | 通常為 1 |
| P | 鐘點 | session.hourly_rate | 每小時費率 |
| Q | 應收金額 | session.total_fee | 時數 × 鐘點 |
| R | 抽成 | session.commission_rate | 0.7 或 0.8 |
| S | 心理師收入 | session.therapist_income | 應收 × 抽成 |
| T | 治療所收入 | session.clinic_income | 應收 − 心理師收入 |
| U | 備註 | session.notes | 備註 |
| V | 給付治療師 | session.therapist_paid | 已付/未付 |

---

## 十、啟動指令

```bash
# 安裝依賴
pnpm install

# 初始化資料庫
cd apps/admin && npx prisma db push && npx tsx prisma/seed.ts && npx tsx prisma/seed-therapists.ts
cd apps/booking && npx prisma db push

# 啟動開發伺服器
pnpm dev:admin    # 內部管理系統 → http://localhost:3001
pnpm dev:booking  # 客戶預約系統 → http://localhost:3000

# 同時啟動兩個系統
pnpm dev
```
