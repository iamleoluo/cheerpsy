# CheerPsy v2 開發工作報告

**專案**：心理診療所營運管理系統（CheerPsy v2）
**報告日期**：2026-05-12
**技術負責**：Leo Luo

---

## 一、專案背景

原系統（v1）為純 Next.js 單體架構，以 SQLite 作為資料庫，部署於 Railway 但缺乏完整的帳務管理、角色控制、報表匯出等核心功能，且無法支撐多角色協作需求。

**本次工作目標**：將系統完整重建為前後端分離架構，實作診所日常營運所需的全部功能模組。

---

## 二、技術架構

### 架構轉型（v1 → v2）

| 項目 | v1（舊） | v2（新） |
|------|---------|---------|
| 架構 | Next.js 單體 | FastAPI + Next.js 14 分離式 |
| 資料庫 | SQLite | PostgreSQL 16 |
| 認證 | 無 / 簡易 | JWT + bcrypt + RBAC |
| 部署 | Railway（單服務） | Railway（API + Web 雙服務） |
| 角色控制 | 無 | admin / accountant / therapist 三級 |

### 技術選型

- **後端**：FastAPI + SQLAlchemy 2.x + Alembic + python-jose
- **前端**：Next.js 14 App Router + Tailwind CSS + Auth.js v5
- **資料庫**：PostgreSQL 16（含 tstzrange 範圍型別做空間衝突檢查）
- **部署**：Docker + Railway（API 和 Web 各獨立 service）

---

## 三、本期完成功能

### 3.1 系統基礎建設（Phase 0）

- [x] 重建 Monorepo 結構（`apps/api/` + `apps/web/`）
- [x] Docker Compose 本地開發環境（PostgreSQL + Redis）
- [x] 完整資料庫 Schema 設計（11 張資料表）
- [x] Alembic migration 管理
- [x] JWT 認證系統（登入、權限驗證、RBAC middleware）
- [x] 種子資料腳本（19 個使用者帳號、13 個治療室）
- [x] Next.js 前端骨架（App Router、Tailwind、Auth.js v5）
- [x] 側邊欄角色分流導航（不同角色看到不同選單）

### 3.2 核心業務模組（Phase 1）

- [x] **個案管理**：CRUD、狀態管理、身份驗證、機構連結
- [x] **預約管理**：單次/批次建立、取消、tstzrange 空間衝突防護
- [x] **空間預約表**：FullCalendar 週視圖，所有使用者的預約均可見
- [x] **機構管理**：機構 CRUD（admin only）

### 3.3 帳務模組（Phase 2）

- [x] **諮商流水帳**：T+1 日結自動建立、70/30 分潤計算
- [x] **自費收款流程**：現金／匯款選擇，匯款需記錄帳戶末五碼
- [x] **機構請款流程**：unpaid → claiming（請款單號）→ claimed（到款收據）
- [x] **帳務鎖定／解鎖**：鎖定後不可修改，管理者解鎖需填寫原因
- [x] **稽核日誌**：所有帳務變更自動記錄（before/after、操作人）
- [x] **收據管理**：開立、作廢（含作廢原因）

### 3.4 報表與分析

- [x] **月報表**：損益摘要（P&L）、KPI（取消率、續診率）、類型統計、資金來源分析
- [x] **財務核銷報表**：按自費／各機構分群，清楚呈現各筆收款狀態
- [x] **CSV 匯出**：流水帳匯出（供每日備份到 Google Drive）

### 3.5 營運輔助功能

- [x] **儀表板**：本月統計、未收款金額、即將到期預約、零用金餘額警示、流失個案預警
- [x] **預約提醒/電訪追蹤**：顯示近期預約，記錄電話聯繫結果（確認/想取消/未接）
- [x] **流失預警**：依天數篩選無後續預約的在案個案，色彩標示嚴重程度
- [x] **心理師酬勞月結**：自動依月份計算應付酬勞，支援標記已付款
- [x] **零用金管理**：收支記錄、類別、餘額追蹤

### 3.6 部署準備

- [x] API Dockerfile（Python 3.11 slim，自動執行 migration）
- [x] Web Dockerfile（Node 18 Alpine 多階段建構，standalone output）
- [x] Railway 部署說明書（完整 checklist + 環境變數速查表）

---

## 四、資料庫 Schema

共 11 張資料表：

| 資料表 | 說明 |
|--------|------|
| `users` | 使用者（admin / accountant / therapist） |
| `cases` | 個案（含身份證加密、機構連結） |
| `rooms` | 治療室（3 層樓共 13 間） |
| `appointments` | 預約（tstzrange 空間衝突防護） |
| `session_records` | 諮商流水帳（T+1 日結） |
| `invoices` | 收據 |
| `therapist_payouts` | 心理師酬勞月結 |
| `payout_details` | 酬勞明細（payout ↔ session） |
| `petty_cash` | 零用金收支 |
| `audit_log` | 稽核日誌（JSONB before/after） |
| `reminder_log` | 電訪追蹤記錄 |

---

## 五、使用者帳號

| 角色 | 帳號 | 密碼 | 數量 |
|------|------|------|------|
| 管理者 | `admin@cheerpsy.com` | `admin123` | 1 |
| 會計 | `accountant@cheerpsy.com` | `staff123` | 1 |
| 心理師 | `t001@cheerpsy.com` ~ `t017@cheerpsy.com` | `therapist123` | 17 |

---

## 六、API 端點總覽

| 模組 | 端點前綴 | 主要功能 |
|------|---------|---------|
| 認證 | `/auth` | 登入、取得目前使用者 |
| 儀表板 | `/dashboard` | 統計數據 |
| 個案 | `/cases` | CRUD |
| 預約 | `/appointments` | 建立、取消、空間查詢 |
| 空間 | `/rooms` | CRUD |
| 流水帳 | `/ledger` | 列表、收款、請款、鎖定、解鎖、日結 |
| 收據 | `/invoices` | 開立、作廢 |
| 機構 | `/institutions` | CRUD |
| 零用金 | `/petty-cash` | 記錄、統計 |
| 報表 | `/reports` | 月報、核銷 |
| 提醒 | `/reminders` | 即將到期預約、電訪記錄 |
| 流失預警 | `/churn` | 無後續預約的個案清單 |
| 酬勞 | `/payouts` | 月結、付款 |
| 稽核 | `/audit` | 操作日誌查詢 |
| 匯出 | `/export` | CSV 匯出 |

---

## 七、待辦事項（後續階段）

### Phase 3（近期）
- [ ] 身份證 AES-GCM 加密實作（資料欄位已預留）
- [ ] PDF 收據/請款單產生
- [ ] Excel 格式月報匯出

### 長期優化
- [ ] 推播通知（預約前日提醒心理師）
- [ ] 個案追蹤備註（每次諮商紀錄）
- [ ] 收費標準設定（目前固定寫在前端）

---

## 八、版本紀錄

| Commit | 內容 |
|--------|------|
| `0e430e6` | v2 系統骨架重建（FastAPI + Next.js 14） |
| `77bdc8d` | 7 大模組完整實作 |
| `840b2aa` | 機構管理、收款流程、空間預約、側邊欄優化 |
| `0b2aa6e` | 儀表板、提醒、流失預警、酬勞、稽核、核銷報表、收款方式、Dockerfile |
