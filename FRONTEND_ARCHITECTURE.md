# CheerPsy 前端架構參考文件

> **用途**：給 AI agent 和開發者參考。描述前端「需要什麼資料」，不限制底層怎麼實作。
> **備份 tag**：`template-v1`（完整原始碼快照）
> **注意**：這份文件是參考，不是規格書。底層資料結構可以自由重新設計，只要最終 API 回傳的 JSON 格式能餵給前端就好。欄位可以增刪改，前端頁面也會配合調整。

---

## 技術棧

| 層級 | 技術 |
|------|------|
| Monorepo | Turborepo + pnpm workspaces |
| 框架 | Next.js 14 (App Router) |
| 認證 | NextAuth.js (JWT strategy) |
| UI | Tailwind CSS + shadcn/ui (Radix) |
| 圖表 | Recharts (透過 wrapper `@/components/charts.tsx`) |
| 驗證 | Zod (共用 schemas) |
| 部署 | Railway (兩個獨立 service) |

---

## 應用結構

```
apps/
  admin/    → 內部管理後台 (port 3001)
  booking/  → 公開預約平台 (port 3000)
packages/
  shared/   → 共用型別、Zod schemas、常數
```

---

## Admin 後台

### 認證與權限

- NextAuth credentials provider，JWT session
- 三種角色：`admin`（完整權限）、`accountant`（財務相關）、`therapist`（自己的排程/預約）
- Middleware 做 route-level 存取控制

### 頁面 → API 對照表

| 頁面 | 路由 | API 呼叫 | 說明 |
|------|------|----------|------|
| 登入 | `/login` | NextAuth `signIn('credentials')` | email + password |
| 總覽 | `/dashboard` | Server-side Prisma（計數查詢） | 顯示 session/therapist/client 數量 |
| 預約管理 | `/bookings` | `GET /api/bookings?status=` | 列表 + 核准/拒絕 |
| 個案管理 | `/clients` | `GET /api/clients?search=` | 搜尋個案 |
| 排程表 | `/schedule` | `GET /api/sessions?page=&limit=&therapistId=&dateFrom=&dateTo=` | 分頁列表 |
| 月曆 | `/schedule/calendar` | `GET /api/sessions?dateFrom=&dateTo=&limit=1000` | 整月資料 |
| 新增紀錄 | `/sessions/new` | `POST /api/sessions` | 表單建立 |
| 編輯紀錄 | `/sessions/[id]` | `GET/PUT/DELETE /api/sessions/{id}` | CRUD |
| 收款管理 | `/finance` | `GET /api/finance?filter=&therapistId=`、`PATCH /api/finance` | 批次更新收款狀態 |
| 心理師管理 | `/therapists` | `GET/POST /api/therapists`、`PUT /api/therapists/{id}` | CRUD |
| 帳號管理 | `/users` | `GET/POST /api/users`、`DELETE /api/users/{id}` | Staff CRUD |
| Excel 匯入 | `/import` | `POST /api/import/preview`、`POST /api/import` | FormData 上傳 |
| 設定 | `/settings` | `PATCH /api/users/{id}` | 改密碼 |
| 薪資核發 | `/reports/therapist` | `GET /api/reports/therapist?dateFrom=&dateTo=` | 心理師收入報表 |
| 治療所收入 | `/reports/clinic` | `GET /api/reports/clinic?dateFrom=&dateTo=` | 治療所收入+圖表 |
| 收費分析 | `/reports/billing` | `GET /api/reports/billing?dateFrom=&dateTo=` | 各收費類型分析 |

### 前端期望的 API 回傳格式

以下是前端頁面目前消費的資料形狀。重構後只要 API 回傳相容的 JSON，前端就能直接對接。

#### Bookings (預約)

```typescript
// GET /api/bookings
interface BookingItem {
  id: string
  client_name: string
  client_phone: string | null
  client_email: string | null
  therapist_name: string | null
  internal_therapist_id: string | null
  requested_date: string        // ISO date
  requested_time_slot: string
  preferred_format: 'in_person' | 'online'
  status: 'pending' | 'confirmed' | 'rejected' | 'cancelled'
  rejection_reason: string | null
  notes: string | null
  created_at: string
}

// POST /api/bookings/{id}/approve → body: { therapistId: string }
// POST /api/bookings/{id}/reject  → body: { reason: string }
```

#### Sessions (治療紀錄)

```typescript
// GET /api/sessions → { sessions: SessionRecord[], total: number }
interface SessionRecord {
  id: string
  date: string
  room: string | null
  therapist: { id: string; name: string }
  client: { id: string; name: string }
  billingType: string | null
  counselingFormat: string | null
  hours: number | null
  totalFee: number | null
  paymentStatus: '已收' | '未收' | null
  therapistPaid: '已付' | '未付' | null
}

// POST /api/sessions — 建立紀錄的完整表單欄位：
interface SessionFormData {
  date: string              // YYYY-MM-DD
  room: string
  therapistId: string
  clientId: string
  billingType: string
  amountReceivable: string
  receivableType: string
  location: '治療所' | '外訪到宅'
  paymentStatus: '未收' | '已收'
  amountReceived: string
  institutionMonth: string
  counselingFormat: '實體' | '視訊'
  counselingType: string
  hours: string             // number as string
  hourlyRate: string        // number as string
  totalFee: string          // auto: hours * hourlyRate
  commissionRate: string    // 0-1, default 0.8
  therapistIncome: string   // auto: totalFee * commissionRate
  clinicIncome: string      // auto: totalFee - therapistIncome
  notes: string
  therapistPaid: '未付' | '已付'
}
```

#### Clients (個案)

```typescript
// GET /api/clients
interface ClientItem {
  id: string
  name: string
  phone: string | null
  email: string | null
  notes: string | null
}
```

#### Therapists (心理師)

```typescript
// GET /api/therapists
interface TherapistItem {
  id: string
  name: string
  commissionRate: number     // 0-1
  isActive: boolean
  bio: string | null
  specialties: string | null
}
```

#### Staff Users (帳號)

```typescript
// GET /api/users
interface StaffUserItem {
  id: string
  email: string
  name: string
  role: 'admin' | 'accountant' | 'therapist'
  therapistId: string | null
  createdAt: string
}
```

#### Finance (收款)

```typescript
// GET /api/finance → { sessions: FinanceSession[], summary: FinanceSummary }
interface FinanceSession {
  id: string
  date: string
  therapist: { name: string }
  client: { name: string }
  billingType: string | null
  amountReceivable: number | null
  amountReceived: number | null
  paymentStatus: string | null
  therapistIncome: number | null
  therapistPaid: string | null
}

interface FinanceSummary {
  totalReceivable: number
  totalReceived: number
  unpaidToClient: number
  unpaidToTherapist: number
}

// PATCH /api/finance → body: { sessionIds: string[], field: string, value: string }
```

#### Reports (報表)

```typescript
// GET /api/reports/therapist
interface TherapistReport {
  therapistName: string
  byBillingType: Record<string, number>
  totalIncome: number
  tax: number                // 10% of income over 20000
  healthInsurance: number    // 2.11% of income over 20000
  netIncome: number
}[]

// GET /api/reports/clinic
interface ClinicReport {
  totalRevenue: number
  totalClinicIncome: number
  totalTherapistIncome: number
  totalSessions: number
  byTherapist: { name: string; income: number }[]
  byBillingType: { type: string; amount: number }[]
  trend: { date: string; revenue: number; clinicIncome: number; sessions: number }[]
}

// GET /api/reports/billing
interface BillingReport {
  selfPay: { count: number; total: number }
  institution: { count: number; total: number }
  byType: { type: string; count: number; therapistIncome: number; clinicIncome: number; totalFee: number }[]
  byTherapistType: { therapist: string; types: Record<string, number>; total: number }[]
}
```

#### Import (Excel 匯入)

```typescript
// POST /api/import/preview (FormData: file)
interface ImportPreview {
  sheetName: string
  totalRows: number
  therapistCount: number
  clientCount: number
  therapists: string[]
  preview: {
    rowNumber: number; date: string; therapist: string; client: string
    billingType: string; hours: number | null; totalFee: number | null; paymentStatus: string
  }[]
}

// POST /api/import (FormData: file + mode:'append'|'replace')
interface ImportResult {
  success: boolean
  imported: number
  skipped: number
  therapists: number
  clients: number
}
```

---

## Booking 預約平台

### 認證

- NextAuth credentials provider，JWT session
- 客戶自行註冊帳號

### 頁面 → API 對照表

| 頁面 | 路由 | API 呼叫 | 說明 |
|------|------|----------|------|
| 首頁 | `/` | Server-side Prisma | 顯示 6 位接受預約的心理師 |
| 登入 | `/login` | NextAuth `signIn('credentials')` | email + password |
| 註冊 | `/register` | `POST /api/auth/register` | 建立客戶帳號 |
| 心理師列表 | `/therapists` | Server-side Prisma | 全部心理師 + 可預約時段 |
| 預約 | `/booking` | `GET /api/therapists`、`POST /api/appointments` | 表單建立預約 |
| 我的預約 | `/my-appointments` | `GET /api/appointments`、`PATCH /api/appointments/{id}` | 查看/取消預約 |

### 前端期望的資料格式

```typescript
// 心理師 (含時段)
interface TherapistProfile {
  id: string
  name: string
  specialties: string | null
  bio: string | null
  isAcceptingBookings: boolean
  availability: {
    id: string
    dayOfWeek: number        // 0=Sunday ~ 6=Saturday
    startTime: string        // "09:00"
    endTime: string          // "17:00"
  }[]
}

// 預約表單
interface AppointmentForm {
  therapistProfileId?: string
  requestedDate: string       // YYYY-MM-DD
  requestedTimeSlot: string   // "09:00"
  preferredFormat: 'online' | 'in_person'
  clientName: string
  clientPhone?: string
  clientEmail?: string
  notes?: string
}

// 我的預約列表
interface AppointmentItem {
  id: string
  requestedDate: string
  requestedTimeSlot: string
  preferredFormat: 'online' | 'in_person'
  status: 'pending' | 'confirmed' | 'rejected' | 'cancelled'
  therapistProfile: { name: string } | null
  clientName: string
  notes: string | null
  rejectionReason: string | null
  createdAt: string
}

// 客戶註冊
interface RegisterForm {
  email: string
  password: string
  name: string
  phone?: string
}
```

### 可預約時段（前端硬編碼）

```
09:00, 10:00, 11:00, 13:00, 14:00, 15:00, 16:00, 17:00, 18:00, 19:00
```

---

## 跨服務通訊

- Admin → Booking 透過 HTTP 呼叫 `/api/internal`
- 驗證：`x-internal-secret` header + `timingSafeEqual`
- `booking-client.ts` 有 fallback：先試 private URL，失敗再試 public URL

---

## UI 組件清單

### Admin
- `sidebar.tsx` — 側邊導覽（依角色顯示不同選單）
- `charts.tsx` — Recharts wrapper（避免 dynamic import 問題）
- `providers.tsx` — NextAuth SessionProvider
- `ui/` — badge, button, card, input, label, select, table

### Booking
- `navbar.tsx` — 頂部導覽（依登入狀態顯示）
- `providers.tsx` — NextAuth SessionProvider
- `ui/` — badge, button, card, input

---

## 導覽結構（角色對應）

### Admin 角色
總覽 → 預約管理 → 排程表 → 新增紀錄 → 收款管理 → 薪資核發 → 治療所收入 → 收費分析 → 心理師管理 → 個案管理 → Excel匯入 → 帳號管理

### Accountant 角色
總覽 → 排程表 → 收款管理 → 薪資核發 → 治療所收入 → 收費分析

### Therapist 角色
總覽 → 我的預約 → 我的排程

---

## 商業邏輯常數

```
稅率 (TAX_RATE):             10%
健保費率 (HEALTH_INSURANCE_RATE): 2.11%
預設抽成比 (DEFAULT_COMMISSION_RATE): 80% (心理師拿)
```

薪資計算邏輯：
- `therapistIncome = totalFee × commissionRate`
- `clinicIncome = totalFee - therapistIncome`
- `tax = (income > 20000) ? income × 0.10 : 0`
- `healthInsurance = (income > 20000) ? income × 0.0211 : 0`
- `netIncome = totalIncome - tax - healthInsurance`
