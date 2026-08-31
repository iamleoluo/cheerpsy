# CheerPsy 現況 vs 原型 v7 落差盤點（gap analysis）

> 產出日期：2026-08-31（v2，依 `open_questions.md` 修訂）
> 基準 commit：`5ccd36d`
> 本文件為**盤點**，不含任何程式碼修改。

---

## 0. 輸入來源與決策原則

| 來源文件 | 角色 |
|---|---|
| `cheerpsy_v7_spec_extracted.md` | 原型 v7 每頁的頁面邏輯與定案（畫面與互動細節） |
| `系統架構new.md` | GitMind 心智圖（業務規則） |
| `open_questions.md` | 衝突與待決清單，Q1–Q23 |

**決策原則（2026-08-31 定）：原型與心智圖相撞時，一律以心智圖為準。** 原型負責畫面與互動細節，心智圖負責業務規則。

**本次新增定案（使用者 2026-08-31）：**
- **D1 — 心理師預約可填當次金額。** 依心智圖優先，衝突 A 解除。預設值帶 `users.base_price`；同一個案若改過價，之後預約以**該個案上次金額**為預設。
- **D2 — `claim_batches.type = self_pay` 廢除。** 月結不再做成核銷案，改走應收帳冊「月結」分頁。

原型共 **20 頁**（行政端 12 + 心理師端 8），`cheerpsy_v7_spec_extracted.md` 的目錄亦為 20 節。先前提到的「21 頁」與兩份文件皆對不上，本文件以 20 頁為準。

<details>
<summary>原型 20 頁清單</summary>

- 行政端（12）：`dash` 營運總覽 · `match` 媒合管理 · `cases` 個案管理 · `rooms` 診間日曆 · `booking` 預約作業 · `appts` 預約總表 · `contracts` 機構合約清冊 · `plans` 機構方案清冊 · `claims` 機構核銷案 · `daily` 日報表/對帳 · `ar` 應收帳冊 · `analytics` 數據分析
- 心理師端（8）：`today` 我的今日 · `sched` 我的班表 · `booking` 預約作業 · `pool` 派案邀請 · `cases` 我的個案 · `docs` 文件確認 · `pay` 我的酬勞 · `stats` 我的數據

> **月報表**是心智圖新增、原型沒有的模組（`open_questions.md` §心智圖新增），故實際要做 **21 頁**（20 + 月報表）。
</details>

---

## 1. Schema 落差

現況：18 個 model（`apps/api/app/models/`），共 481 行。整體資料骨架相當成熟——預約、日結帳冊、核銷案、收據、伴侶案、機構扣打都已存在。落差集中在**三個結構性問題**：

1. **機構只有一層**（`institutions`），原型要三層：機構 → 合約 → 方案。
2. **媒合流程完全不存在**（0 model、0 router、0 頁面）。
3. **金額只有一個欄位**（`session_records.amount`），全程需要「個案自付額 / 機構請款額」雙欄。

### 1.1 要新增的表

| # | 新表 | 用途 | 來源 |
|---|---|---|---|
| 1 | `referral_requests` | 諮商需求表 / 媒合案主體。派案碼 `YYMMDD+3碼`、姓名年齡性別電話、管道來源、主述議題、議題補充說明、諮商型態、收費模式、媒合狀態 | 原型 `match`；心智圖 §一.2.2 |
| 2 | `referral_dispatches` | 派案批次（子列表一列＝一批次）：第幾次、派出時間、批次狀態 | 原型 `match` 定案⑤ |
| 3 | `referral_dispatch_targets` | 一批次派給 1–3 位心理師，各自回覆狀態（待回覆／承接／婉拒／被他人承接／**已退回**／承接後釋出）、婉拒原因、逾期提醒時間 | 原型 `pool` 定案④；心智圖新增「已退回」 |
| 4 | `referral_slot_offers` | 心理師承接時提供的 1–3 個可預約時段（第一個必填） | 原型 `pool` 定案③ |
| 5 | `institution_contracts` | 機構合約層：方案鐘點費、個案自付額、身份條件、核銷上限（金額／次數／不限）、承辦人、電話、合約有效期、**核銷區間匯入** | 原型 `contracts`；心智圖 §三.1；Q「是否匯入核銷區間」＝**是** |
| 6 | `institution_plans` | 機構方案層：核銷單位／窗口／電話、每人次數、年度總次數（可「不限」）、有效起訖、備註、狀態（使用中／已用罄／已過期） | 原型 `plans`；心智圖 §三.2 |
| 7 | `plan_transport_fees` | **方案層交通費模式**。心智圖：「每方案交通費模式不同，可直接帶出讓心理師選擇」→ 一方案可有多個選項，故 1:N。欄位：`plan_id`／`label`／`amount`／`is_default` | 心智圖 §二「選方案時帶出」 |
| 8 | `claim_batch_plans` | **核銷案 ↔ 方案 1:N 連結表**。Q3 定案：一個核銷案可同時選多個方案一起核銷 | Q3 |
| 9 | `claim_documents` | 心理師依核銷案上傳的附件三類：領據／月次清冊表／其他（帳戶、證照、同意書） | 心智圖 §三.3；open_questions 已定案 |
| 10 | `daily_closings` | 每日對帳：日期、狀態（待對帳／已完成）、現金總額、匯款總額、完成者與時間、**是否鎖定** | 心智圖 §四.4；Q「對帳後鎖定」＝**是** |
| 11 | `monthly_reports` | 月報表表頭，**只存不可推導的欄位**：`month`(YYYY-MM)／`status`／`finalized_at`／`payout_date`。已對帳天數、合計金額、心理師收入**全部即時推導**自 `daily_closings`（月份由 `daily_closings.date` 推得，不需反向外鍵） | 心智圖 §四.4（原型無此模組） |
| 12 | `supervisor_reviews` | **主管覆核紀錄**：對帳鎖定後解鎖修改的紀錄。欄位：`daily_closing_id`／`session_record_id`／`unlock_reason`／`unlocked_by`／`unlocked_at`／`reviewed_by`／`reviewed_at`。補收款**不**進本表 | 心智圖 §四.4；Q「解鎖修改列入主管覆核紀錄」 |
| 13 | `holidays` | 國定假日，供批次預約標示提醒（不自動跳過） | 原型 `booking` 定案② |
| 14 | `therapist_availability` | 心理師每週可當診時段（上午 0800-1200／下午 1300-1700／晚上 1800-2100） | 心智圖 §一.4；原型 `stats` |
| 15 | `events` | 講座／活動／場地租借（**本輪排除**，見 §3.3） | 心智圖 §二 |

> `quota_templates`（現有）與 `institution_plans` 高度重疊，建議**升級改寫**而非並存，否則會有兩套「方案」定義。

> **月報表的單一真相鏈**：`session_records.daily_closing_id` → `daily_closings.date` → 月份。
> `session_records` **不**掛 `monthly_report_id`——那會讓同一筆紀錄有兩條路徑歸屬到月份，對帳日期一改就可能不一致。`monthly_reports` 只是「這個月是否已定版、何時發薪」的狀態表，金額一律由 `daily_closings` 即時聚合。

### 1.2 稽核與覆核：可重用既有機制

| 需求 | 建議 | 理由 |
|---|---|---|
| **鐘點費回溯修改稽核**（Q4） | ✅ **重用 `audit_log`** | 現有欄位 `table_name`／`record_id`／`operation`／`before_data` JSONB／`after_data` JSONB／`changed_by`／`reason` 已完全滿足「誰、何時、舊值→新值、原因」。寫入 `table_name='session_records'`、`operation='UPDATE'` 即可，不需新表 |
| **酬勞手動調整稽核**（Q22） | ✅ **重用 `audit_log`** | 同上，`table_name='payout_details'` |
| **主管覆核紀錄** | ❌ **需新表 `supervisor_reviews`** | 這是**業務流程**（要有人覆核、要能列出待覆核清單、要能查詢當月覆核例外），不只是稽核軌跡。`audit_log` 沒有「覆核人／覆核時間」與待辦語意 |

### 1.3 `invitations` 能否重用於派案邀請？（已檢查）

**結論：不能，需新建 `referral_dispatch_targets`。**

現有 `invitations` 欄位：`invite_key`／`type`(invite\|reset)／`name`／`role`／`user_code`／`target_user_id`／`created_by`／`created_at`／`expires_at`／`used_at`。

| 派案邀請需要 | `invitations` 是否有 |
|---|---|
| 關聯到 `referral_request` | ❌ 無任何業務關聯欄位 |
| 6 種回覆狀態（待回覆／承接／婉拒／被他人承接／已退回／承接後釋出） | ❌ 只有 `used_at` 是/否兩態 |
| 婉拒原因（四選一＋其他） | ❌ 無 |
| 逾 1 天提醒、逾 3 個自然日自動退回 | ⚠️ `expires_at` 語意近似但只有一個門檻，無法表達「提醒」與「退回」兩段 |
| 同一批次派 1–3 人、先回先得 | ❌ 無批次概念 |

`invitations` 是**帳號開通／密碼重設的一次性 token**，生命週期是「發出→被使用→失效」。派案邀請是**業務流程狀態機**，會被別人搶走、會被退回、會有原因。兩者共用 `expires_at`／`used_at` 會讓帳號邀請與派案邀請的語意糾纏，維護成本高於新建一張表。**`invitations` 維持原用途不動。**

### 1.4 要加欄位的既有表

| 表 | 新增欄位 | 理由 |
|---|---|---|
| `cases` | `referral_id` FK、`dispatch_code`（派案碼，與病歷號並存以利追溯）、`chief_complaint`、`complaint_note`、`consultation_mode`、`group_name`、`group_representative` | 原型 `match` 編號規則；心智圖 §二諮商型態 |
| `couple_members` → **`case_members`** | 更名 ＋ `role` 列舉擴充：案主／配偶／**相對人**（會面交往）／**團體成員**。**改名屬破壞性變更，排在 Phase 1** | 心智圖 §二：伴侶諮商與**會面交往**皆需輸入 2 位個案姓名——與伴侶案同構，現有表可直接擴充 |
| `appointments` | `fee_item`（諮商項目）、`plan_id` FK、`transport_fee`、`transport_fee_option_id` FK、`video_link`、`notify_admin_to_forward`、`forwarded_at`、`outreach_location`、`checkin_status`、`no_show_type`、`no_show_fee`、`hourly_rate`（**當次金額，D1**） | 心智圖 §二；原型 `rooms` 定案⑥ |
| `case_institution_quotas` | `reserved_count`（已預留）、`booked_count`（已預約）、`plan_id` FK、`status`（使用中／已用罄／已結案／封存） | **原型 `plans` 核心**：恆等式 `已使用 + 已預約 + 已預留 = 個人上限`。現況只有 `total_count`／`used_count` 兩態 |
| `session_records` | `self_pay_amount`、`institution_claim_amount`（拆分現行單一 `amount`）、`fee_item`、`daily_closing_id` FK、`is_no_show`、`no_show_fee`、`rejected_at`、`rejected_reason`、`supplementary_paid_at`（補收款）。**`receipt_no` 廢除，改 `invoice_id` FK** — 見 §1.5 | 原型 `claims`／`ar`／`daily`；心智圖 §四.4 |
| `invoices` | `branch_code`（館別 A）、`category`（C 諮商／O 其他）、`print_seq`、`check_code`（-1 開立／-2 重印／-3 作廢）。**`appointment_id` 改為 nullable**（商品販售分類 O 無預約），新增 `session_record_id`／`product_sale_id` 二擇一 | 心智圖 §四.1 |
| `claim_batches` | `void_reason`／`voided_at`／`voided_by`；status 擴充；**`institution_id` 保留、方案關聯改走 `claim_batch_plans`**（Q3） | 原型 `claims`；Q3 |
| `therapist_payouts` | 拆為 `counseling_income`／`lecture_fee`／`supervision_income`／`venue_deduction`／`total` 五欄 | 心智圖 §四.4 |
| `payout_details` | `amount`（可手動編輯，Q22）、`is_manually_adjusted`、`rate_changed_flag`（鐘點費變動提示，不改值） | Q22 定案：不自動重算，人工調整 |
| `users` | `role` 可能需增 `intern`（Q7 未定） | 心智圖 §一.2.2 |
| `rooms` | `room_type`（晤談／兒童遊戲室） | 原型 `rooms` 定案①：12 間，僅 2C、2E 為兒童遊戲室 |

**諮商型態列舉（心智圖 §二完整定義）：**
個人諮商 → `individual`（個人一對一）／`couple`（伴侶，需 2 位）／`visitation`（**會面交往**，需 2 位）／`family_group`（親子／團體，需團體名稱＋代表人）
外展 → `outreach_individual`／`outreach_group`／`lecture`（講座／活動）

**諮商項目列舉（連動收據名目）：**
`psychotherapy` 心理治療／`counseling` 心理諮商／`visitation` 會面交往／`summary_report` 摘要報告／`other` 其他（會談／專業評估／人際互動治療／工作坊）

### 1.5 要改語意的既有欄位

⚠️ **這些全部集中在 Phase 1 一次做完**（見 §4）。分批做會讓中間狀態的資料無法解讀。

| 欄位 | 現況語意 | 新語意 | 影響 |
|---|---|---|---|
| `cases.billing_cycle`、`cases.funding_source` | 個案層**固定設定**，預約時沿用 | 降級為**預設值**；實際由心理師在每次預約當下選填 | 原型 `cases` 定案①②、心智圖 §一.3。既有資料不需搬，但讀取邏輯要改看 `appointments` |
| `appointments.status` | `booked`／`executed`／`cancelled` | 需區分「已預約／已到／**未到**／已取消」——現況無法表達「未到」，只能記 cancelled，丟失失約費與額度釋回依據 | 需 migration 決定既有 cancelled 如何回填 |
| `session_records.amount` | 單一總金額 | 拆為 總額／自付額／機構請款額 | 既有機構案紀錄需回算拆帳 |
| `session_records.payment_status` | `unpaid`／`paid`／`claimed` | 應收帳冊三分頁分的是**追款方式**（未收／月結／機構），不是狀態。需區分「該當場收卻沒收到」vs「本來就月結」 | 現況 `unpaid` 混合兩種情況，日報表「當日應收未收」會算錯。**另：`import_excel.py:290` 寫入 `pending_claim`，此值不在文件化 enum 內，屬既有錯誤，一併修正** |
| `cases.status` = `lost` | 儲存值 | 心智圖定義「預警流失＝超過 45 天未有預約紀錄」是**衍生規則** | 需決定改 computed 或保留為快照；兩者並存會不一致 |
| `institutions` | 一個機構一筆，含 `requires_therapist_docs` | 降為三層最上層；鐘點費／自付額／承辦人／上限全部搬到 `institution_contracts` | `case_institution_quotas.institution_id` 改指向 `plan_id` |
| **`claim_batches.type = self_pay`** | 自費月結也做成核銷案 | **廢除（D2）**。月結改走應收帳冊「月結」分頁 | 既有 `type='self_pay'` 的 batch 需資料遷移或封存；`/claims` 的 `SelfPayTab` 整段移除 |

#### 收據單一真相的遷移方案

現況有**三個地方各記一份收據編號**，彼此沒有外鍵關聯：

| 位置 | 格式 | 產生點 |
|---|---|---|
| `invoices.invoice_number` | 自訂 | `invoices` 表（目前僅綁 `appointment_id`） |
| `session_records.receipt_no` | `R{YYYYMMDD}{seq:04d}` | `services/settlement.py:49 next_receipt_no()` |
| `product_sales.receipt_no` | `P{YYYYMMDD}{seq:04d}` | 商品販售流程 |

同一次諮商可能在 `invoices` 和 `session_records` 各留一個號，**兩者不保證一致**，且 `services/pdf/receipt.py` 有 `record.receipt_no or f"R{record.id}"` 這類 fallback，等於第四種號。新的檢核碼機制（`-1` 開立／`-2` 重印／`-3` 作廢）**必須有單一權威來源**，否則重印次數會算錯。

**遷移步驟（Phase 1 執行）：**

1. `invoices` 加 `session_record_id`／`product_sale_id`（二擇一，加 CHECK 約束），`appointment_id` 改 nullable。
2. **回填**：為每筆 `session_records.receipt_no IS NOT NULL` 的紀錄建一列 `invoices`，`invoice_number` **原樣沿用舊值**（`R...`／`P...`），`check_code` 填 `1`、`print_seq` 填 `0`；`product_sales` 同理。
3. `session_records.invoice_id`／`product_sales.invoice_id` 回寫。
4. **保留** `session_records.receipt_no` 一個版本當只讀備援（標 deprecated），確認 `/daily`、`/ar`、PDF 三處都改讀 `invoices` 後，下個 Phase 再 drop。
5. 新號產生器只認新格式 `A{YYYYMMDD}{C|O}{seq3}-{1|2|3}`；**舊 `R`／`P` 號不重編**，產號器依當日 `invoices` 中**新格式**的筆數取流水號，跳過舊格式。
6. `services/pdf/receipt.py` 的 `or f"R{record.id}"` fallback **移除**——沒有 invoice 就不該印收據，靜默造號比報錯更危險。
| **收據：兩套並存** | `invoices.invoice_number` **和** `session_records.receipt_no` 各記一份，`product_sales.receipt_no` 又是第三份 | **`invoices` 為單一真相**。`session_records.receipt_no` 廢除，改 `invoice_id` FK；`product_sales.receipt_no` 同樣改 `invoice_id` FK | 見下方遷移方案 |

---

## 2. 前端頁面落差（現有 11 路由 vs 目標 21 頁）

現況共 11,981 行，全部是**行政視角**，沒有心理師端殼層——`sidebar.tsx` 只用 `roles` 陣列過濾同一份選單，`layout.tsx` 也只有單一 shell。目標是**兩套完全不同的導覽**（行政 13 項分 5 群組／心理師 8 項）。

### 2.1 可改（保留檔案，內容重寫或拆分）

| 現有路由 | 行數 | 對應頁 | 改動性質 |
|---|---|---|---|
| `/dashboard` | 258 | `dash` 營運總覽 | **中改**。KPI 換成 媒合數／進案數／進案率／預約達成率／本月應收；新增「今日待辦」（可就地執行）與「來源分析」 |
| `/cases` | 3364 | `cases` 個案管理 | **大拆**。目前一頁塞了個案＋預約＋額度＋範本四件事。留下的 `cases` 只做**三分頁**：最新動態／預約歷程／個人資料（**Q5 定案：不設「款項紀錄」分頁**），外加預警流失列表 |
| `/calendar` | 847 | `rooms` 診間日曆 | **重寫**。現為 by_room／by_slot／reminders；改為櫃檯主控台：12 診間 × 08:00–22:00 × 30 分半格，方塊上完成 報到→收款→開收據 |
| `/ledger` | 727 | `daily` 日報表/對帳 | **中改**。加「完成當日對帳」寫入 `daily_closings` 並**鎖定**；`history` 分頁併入 `appts`／`ar` 的區間查詢 |
| `/claims` | 1350 | `claims` 機構核銷案 | **重組**。`SelfPayTab` **整段移除**（D2）、`DocConfirmTab` 搬到心理師端 `docs`；本頁改為 4 分頁：核銷案列表／建立核銷案／文件狀態與退件／作廢處理 |
| `/finance` | 1240 | 三處 | **拆解**。`tracking`→`ar`、`payouts`→心理師端 `pay`、`petty`（零用金）原型未涵蓋，留在 `/admin` |
| `/reports` | 1630 | `analytics` 數據分析 | **中改**。補留案率、黏著度、媒合成功率、空間使用率四個指標 |
| `/products` | 238 | 併入 `daily` | 商品販售是日報表的「分類 O」，不是獨立頁。可保留為管理入口 |

### 2.2 要新建

| 新路由 | 對應 | 內容來源 |
|---|---|---|
| `/match` | `match` 媒合管理（3 分頁） | **全新** |
| `/contracts` | `contracts` 機構合約清冊 | **全新** |
| `/plans` | `plans` 機構方案清冊 | 由 `cases` 的 `QuotasTab`+`TemplatesSection`（約 900 行）抽出，補合約層與額度三態 |
| `/appts` | `appts` 預約總表 | 由 `cases` 的 `AppointmentsTab`（約 150 行）抽出 |
| `/booking` | `booking` 預約作業 | 由 `cases` 的 `AppointmentForm`+`BatchForm`（約 1000 行）抽出。**第 4 分頁「5F 雲燈教室」本輪排除** |
| `/ar` | `ar` 應收帳冊（未收／**月結**／機構） | 由 `finance` 的 `tracking` 抽出擴充；月結分頁承接原 `claims` 的 `SelfPayTab` 職責（D2） |
| **`/monthly`** | **月報表（心智圖新增，原型無）** | **全新**。每日對帳彙總（可展開明細）、心理師當月收入五欄、主管覆核紀錄、當日應收未收、優待減免 |
| 心理師端 8 頁 | `today`/`sched`/`booking`/`pool`/`cases`/`docs`/`pay`/`stats` | **全新殼層**。需獨立 route group（如 `(therapist)/`）＋獨立 sidebar＋`layout.tsx` 依 role 分流 |

### 2.3 要刪

沒有該整頁刪除的，落差主要是「拆分與搬移」。三個候選：

- `/claims` 的 `SelfPayTab` — **確定移除**（D2），職責移交 `/ar` 月結分頁。
- `/calendar` 的 `reminders` 分頁（`ReminderLog`）— 原型無此概念，改由「今日待辦」承接。建議**保留資料表**，只從 UI 撤掉。
- `/ledger` 的 `history` 分頁 — 被 `appts`／`ar` 的區間查詢取代。

`/admin`、`/admin/users`、`/settings`、`/guide` 兩份文件皆未涵蓋（屬系統管理），**維持不動**。

### 2.4 共用元件

`sidebar.tsx` 改寫為兩套 nav，`layout.tsx` 依 `session.user.role` 分流。這是所有頁面工作的前置。

---

## 3. 阻擋狀態（依 `open_questions.md` 修訂）

### 3.1 🔴 硬阻擋 — 僅剩一題

| # | 問題 | 衝突內容 | 卡住的範圍 |
|---|---|---|---|
| **Q6** | **15-45 青壯方案的自付額是 $0 還是 $400？** | 心智圖內文：「衛生局/15-45青壯 是機構方案的**機構全額**」（＝自付 $0）；心智圖合約表與原型 `INST` 資料：**$400** | **僅 seed 資料與收據名目**，不阻擋任何模組的結構開發。可先建表、seed 留 TODO |

> 先前列為硬阻擋的**衝突 A（心理師能否改金額）已由 D1 定案解除**；**衝突 C（結帳方式由誰決定）**已由原型定案①解決（不再由行政設定）；**衝突 D（收據重印 vs 重開）**降為 🟡（Q8）。

### 3.2 🟢 已定案，可實作（本次從阻擋移除）

| Q | 定案 | 對盤點的影響 |
|---|---|---|
| **Q1** | 核銷案子列表**可增加／減少個案紀錄**，挑「紀錄」不只挑「人」 | 原型「不可單挑場次、勾人整組納入」的硬規則**取消**。防漏／防重（同一紀錄不可進兩個核銷案、期間內未納入提示）保留為**提示不阻擋** |
| **Q2** | **每月 1 號起只要有方案預約即可建案**，之後每天滾動加入紀錄 | 「期間」改為建案時的**參考區間**；缺口／重疊**不做硬檢查**，上次結束日仍顯示供參考。目的是讓心理師能提早上傳文件 |
| **Q3** | 一個核銷案**可跨方案**，需可同時選其他方案一起核銷 | `claim_batches` ↔ 方案改為 **1:N**（新增 `claim_batch_plans`）。紀錄仍需**先選方案再挑紀錄** |
| **Q4** | 鐘點費**可回溯修改**，需留稽核軌跡 | 重用 `audit_log`（見 §1.2）。修改**不連動**酬勞重算 |
| **Q5** | 個案詳情為**三分頁**：最新動態／預約歷程／個人資料，**不設款項紀錄分頁** | 個案詳情頁**不暴露收款 API**；款項走應收帳冊／日報表／月報表 |
| **Q22** | 鐘點費回溯修改後，酬勞**不自動重算**，由人員手動調整 | `payout_details.amount` 需可手動編輯＋留稽核；鐘點費變動時對已結算列**提示**「請確認酬勞」但不改值 |
| — | 日報表**完成當日對帳後鎖定**；解鎖修改列入**主管覆核紀錄** | 新增 `supervisor_reviews`（§1.1 #12）。補收款自動回寫、**不視為修改、不需解鎖、不列覆核** |
| — | 我的酬勞來源＝**月報表**；結算區間當月 1 日～月末；**隔月 25 日發放** | 新增 `monthly_reports`（§1.1 #11）；`/pay` 依賴 `/monthly` |
| — | 文件確認附件三類：**領據／月次清冊表／其他** | `claim_documents.type` 列舉確定 |
| — | 機構合約**支援核銷區間匯入** | `institution_contracts` 需匯入欄位 |

### 3.3 🟡 可先實作預設值，程式碼標 `TODO(open_questions#Qn)`

不再是阻擋，但實作時要留註解：

| Q | 事項 | 建議預設 |
|---|---|---|
| Q7 | 實習心理師是否進系統供派案 | 先不加 `intern` role，派案對象限 `therapist` |
| Q8 | 收據「重印」vs「重開」判定規則 | 編號格式（`-2`／`-3`）先做；重開判定先只提供「作廢後重開」單一路徑 |
| Q9 | 已預留是否設有效期；個案暫停時預留保留或釋出 | 預留**不設有效期**；暫停時**保留** |
| Q10 | 跨年度未用完額度 | 先做**歸零重算** |
| Q11 | 方案年度總量將滿是否預警 | 先不預警 |
| Q12 | 未到／臨時取消是否計酬；失約費如何分配 | 失約費**先不計入酬勞**（先前的「衝突 B」） |
| Q13 | 酬勞明細是否顯示扣繳稅額與勞健保 | 先不顯示 |
| Q14 | 進案率分母 | 先用「當月新增媒合」，UI 標注 |
| Q15 | 待辦是否需「已讀／延後」 | 先不做 |
| Q18 | 目標收入／人次由誰設定 | 先做全所單一目標 |
| Q19 | 空間使用率分母是否排除未當診時段 | 先用完整營業時段 |
| Q20 | 催繳通知頻率與方式 | 先只做站內待辦 |
| Q21 | 諮商紀錄撰寫是否納入系統 | 先不納入 |
| **Q23** | **酬勞計算每位心理師算法不同，系統支援到哪一層** | 採 `open_questions.md` 的建議 **a)**：以 `commission_rate` × 有效金額為**預設值**，允許**逐筆手動覆寫**＋稽核。與 Q22 一致 |
| **Q24** | **`users.base_price` 調整時套用到所有進行中個案，或僅新案適用** | 心智圖載明兩種心理師都存在，不能寫死。**預設：調價時跳窗讓心理師二選一**（僅新案／全部進行中個案），選擇留稽核。**Phase 3 實作** |

### 3.4 ⛔ 本輪排除

| 模組 | 原因 |
|---|---|
| **講座／活動／場地租借**（`/booking` 第 4 分頁、`events` 表） | **Q16**（講師費是否入慈恩帳戶／是否酌收行政服務費）與 **Q17**（督導收入 A／B 模式、私人租借場地費定義，兩份文件皆無說明）未定。這兩題直接決定 `therapist_payouts` 的 `lecture_fee`／`supervision_income`／`venue_deduction` 三欄語意，先做會白做 |
| **Google 日曆雙向同步** | 原型 `sched` 定案④列為既定需求，但心智圖只提到「視訊／外展會額外掛 Google 日曆」，範圍不一致；需 OAuth 與衝突優先權設計，屬獨立專案 |

---

## 4. 建議開發順序

排序原則：**所有 schema 語意變更集中在 Phase 1 一次做完**，之後每個 Phase 只做加法。這樣中途任何時點的資料都可解讀，且只需一次大 migration。

**部署原則：`main` 在每個 Phase 結束時都必須可部署。** Phase 1 的語意變更會直接打到 `/cases`、`/ledger`、`/claims` 三個既有頁面，而它們的改寫要到 Phase 3–4 才排到。解法見 Phase 1 的「向下相容策略」。

---

### Phase 0 — 導覽與路由骨架

> 純前端，不碰資料庫，不碰任何既有頁面的內容。目的是先把 21 頁的容器立起來，之後每個 Phase 只填內容，避免反覆改 layout。

**表**：無

**頁**：
- `components/sidebar.tsx` 拆為兩套 nav：行政 13 項分 5 群組（營運／個案流程／每日作業／機構／財務／分析），心理師 8 項
- `app/(app)/layout.tsx` 依 `session.user.role` 分流至對應 shell
- 新增 `app/(therapist)/` route group ＋ 其 `layout.tsx`
- 建立空白路由：`/match`、`/contracts`、`/plans`、`/appts`、`/booking`、`/ar`、`/monthly`，以及心理師端 `/today`、`/sched`、`/pool`、`/docs`、`/pay`、`/stats`（心理師端 `/booking`、`/cases` 共用行政元件，Phase 3／6 再分化）
- 每個空白頁放一致的「本頁於 Phase N 實作」佔位卡，標明對應的 Phase

**`import_excel.py` 要跟著改**：無。

**阻擋**：無 ✅

---

### Phase 1 — 資料底層重整（機構三層 ＋ 額度三態 ＋ **全部語意變更**）

> 這是唯一一次破壞性 migration。之後的 Phase 只新增表與欄位，不再改既有欄位的意義。

**表 — 新增**
`institution_contracts`、`institution_plans`、`plan_transport_fees`
`quota_templates` → 升級併入 `institution_plans`

**表 — 加欄位**
`case_institution_quotas` 加 `reserved_count`／`booked_count`／`plan_id`／`status`
`institutions` 瘦身（鐘點費／自付額／承辦人／上限移出至 contracts）

**表 — 語意變更（§1.5 全部，一次做完）**
- `appointments.status` 加「未到」
- `session_records.amount` 拆 `self_pay_amount`／`institution_claim_amount`
- `session_records.payment_status` 重定義（含修正未文件化的 `pending_claim`）
- `cases.billing_cycle`／`funding_source` 降為預設值
- `cases.status = lost` 改衍生規則
- **`claim_batches.type = self_pay` 廢除（D2）**
- `invoices` 收據編號欄位改制 ＋ **收據單一真相遷移六步驟**（§1.5）
- **`couple_members` → `case_members` 改名 ＋ `role` 列舉擴充**（改名是破壞性變更，與其他 DDL 一起做完）

**頁**：`/contracts`（新）、`/plans`（新，由 `cases` 的 `QuotasTab`+`TemplatesSection` 搬出）

#### 🔒 向下相容策略（採方案 a）

Phase 1 動的是 `/cases`、`/ledger`、`/claims` 正在讀的欄位，但這三頁要到 Phase 3–4 才改寫。**Phase 1 必須同時更新 router 與 Pydantic schema，讓舊前端不改一行也能跑。**

| 變更 | 相容作法 |
|---|---|
| `session_records.amount` 拆兩欄 | Pydantic response schema **保留 `amount` 欄位**，用 `@computed_field` 回傳 `self_pay_amount + institution_claim_amount`。舊前端讀到的數字與現在完全一致 |
| `appointments.status` 加「未到」 | Response schema 加 `status_v2`（新值）；`status` 欄位保留舊三值，`no_show` 對舊前端映射為 `cancelled`。**寫入端**接受新舊兩種值 |
| `session_records.payment_status` 重定義 | 同上，`payment_status` 回傳舊三值（新值映射回 `unpaid`/`paid`/`claimed`），新增 `payment_status_v2` |
| `cases.billing_cycle`／`funding_source` 降為預設值 | 欄位不動、繼續回傳。只是**寫入邏輯**改為不再被預約流程當權威來源 |
| `claim_batches.type = self_pay` 廢除 | 既有 `self_pay` batch **不刪**，標 `is_legacy=true`；`/claims` 的 `SelfPayTab` 在 Phase 1 仍能唯讀顯示，Phase 5 才移除 |
| `couple_members` → `case_members` | 建立 `couple_members` 為 **SQL view** 指向新表，舊 query 不會斷 |
| `session_records.receipt_no` → `invoice_id` | 舊欄位**保留為只讀備援**（§1.5 步驟 4），Phase 4 確認三處都改讀 `invoices` 後才 drop |

**驗收條件**：Phase 1 合併後，`/cases`、`/ledger`、`/claims`、`/finance` 四頁在**完全不改前端程式碼**的前提下功能與畫面不變。這是 Phase 1 的 definition of done。

**技術債登記**：上述 `*_v2` 欄位、`couple_members` view、`is_legacy` 旗標、`receipt_no` 備援欄，全部在對應 Phase 改寫完前端後移除。建議開一張 issue 逐項追蹤，避免相容層長期留存。

**`import_excel.py` 要跟著改**：
`get_or_create_institution()` 只建 `Institution`，新結構下需連帶建立 `institution_contract` + `institution_plan`（否則 `case_institution_quotas.plan_id` 無值）；`import_ledger()` 的 `amount` 單欄要拆為自付／請款兩欄；**`payment_status="pending_claim"`（`import_excel.py:290`）是不在 enum 內的既有錯誤，一併改為新列舉**；`import_cases()` 寫入的 `funding_source`／`billing_cycle` 語意降為預設值，註解要更新。

**阻擋**：🟡 Q9／Q10／Q11（額度生命週期例外）先用 §3.3 預設值＋TODO

---

### Phase 2 — 媒合管理

> 定案最完整（原型 `match` ①–⑥、`pool` ①–⑤ 全部拍板），完全新建、不動既有資料，風險最低。

**表 — 新增**：`referral_requests`、`referral_dispatches`、`referral_dispatch_targets`、`referral_slot_offers`
**表 — 加欄位**：`cases` 加 `referral_id`／`dispatch_code`／`chief_complaint`／`complaint_note`／`consultation_mode`
**頁**：`/match`（新，3 分頁）、心理師端 `/pool`（新）

**`import_excel.py` 要跟著改**：舊資料無媒合紀錄，匯入的個案 `referral_id`／`dispatch_code` 留 `NULL`——需確認 Phase 2 的 migration **不要**把這兩欄設成 NOT NULL，否則既有匯入流程會直接失敗。

**阻擋**：無（Q7 實習心理師除外，先限 `therapist`）✅

---

### Phase 3 — 預約與診間日曆

> 把 `cases/page.tsx`（3364 行）拆開，並把日曆改造成櫃檯主控台。

**表 — 新增**：`holidays`
**表 — 加欄位**：`appointments` 加 `fee_item`／`plan_id`／`transport_fee`／`transport_fee_option_id`／`video_link`／`notify_admin_to_forward`／`forwarded_at`／`outreach_location`／`checkin_status`／`no_show_type`／`no_show_fee`／**`hourly_rate`（D1 當次金額）**；`rooms` 加 `room_type` 並補齊 12 間；`cases` 加 `group_name`／`group_representative`

> `case_members` 改名已在 **Phase 1** 完成，此處只用不改。

**頁**：`/booking`（拆出，**3 分頁；第 4 分頁雲燈教室排除**）、`/appts`（拆出）、`/calendar` 重寫為主控台（**報到／未到流程；收款與開立收據按鈕移到 Phase 4**）、心理師端 `/sched`

> **依賴修正**：診間日曆的［收款］［開立收據］依賴 Phase 4 的收據產號器與 `daily_closings`。Phase 3 只做**報到／未到**與額度流轉（已預約→已使用／退回已預留），方塊上先不長出收款按鈕。Phase 4 再補上，屆時「一頁完成報到→收款→開收據」才成立。

**D1 實作要點**：金額預設值優先序 ＝ ① 該個案上次預約的 `hourly_rate` → ② `users.base_price`。心理師可改。
**Q24 實作要點**：心理師調整 `users.base_price` 時**跳窗詢問**套用範圍——「僅新案適用」或「套用到所有進行中個案」（心智圖：兩種心理師都存在）。

**`import_excel.py` 要跟著改**：`import_ledger()` 的 `session_type` 判斷（目前只認「視訊」→ online、「到宅」→ outdoor）要擴充涵蓋**會面交往／團體／外展**；`get_room_map()` 需對應補齊後的 12 間診間代碼，舊 sheet 的房號若對不上要有 fallback 而非靜默丟棄。

**阻擋**：無（衝突 A 已由 D1 解除）✅

---

### Phase 4 — 財務日結、應收帳冊、**月報表**

**表 — 新增**：`daily_closings`、`monthly_reports`（只存 `month`／`status`／`finalized_at`／`payout_date`）、`supervisor_reviews`
**表 — 加欄位**：`session_records` 加 `daily_closing_id`／`is_no_show`／`no_show_fee`／`supplementary_paid_at`；**`therapist_payouts` 拆五欄**（`counseling_income`／`lecture_fee`／`supervision_income`／`venue_deduction`／`total`）
**收據產號邏輯**：欄位已在 Phase 1 建好，此處實作 `A{YYYYMMDD}{C|O}{seq3}-{1|2|3}` 產生器，並完成 §1.5 遷移的步驟 4–6（切換三處讀取來源、drop 舊欄、移除 PDF fallback）

> **依賴修正**：`therapist_payouts` 拆五欄從 Phase 6 **提前到此**。月報表的「心理師當月收入五欄」就是這張表的投影，兩者必須同時存在，否則 `/monthly` 只能做半頁。Phase 6 只做心理師端的 `/pay` 讀取畫面與 `payout_details` 的手動覆寫。

**頁**：`/ledger` → `/daily` 改寫（加對帳鎖定）、`/ar`（新，3 分頁，**月結分頁承接原 SelfPayTab**）、**`/monthly`（新）**、`/calendar` **補上［收款］［開立收據］**（Phase 3 移交）

**月報表規則（心智圖 §四.4）**：資料來源**只有** `daily_closings` 中已完成對帳的日；未對帳的日標「待對帳」，金額不計入合計、不進心理師收入；補收款自動回寫該日並標小字「MM/DD 補收 $X」，不視為修改、不需解鎖、不列主管覆核。

**`import_excel.py` 要跟著改**：`import_ledger()` 匯入的歷史紀錄 `daily_closing_id`／`monthly_report_id` 留 `NULL`，並需在 `/monthly` 明確標示為「歷史匯入，未對帳」，避免被算進當月合計；既有 `receipt_no`（舊 `R{YYYYMMDD}{seq}` 格式）**保留不重編**，產號器需能跳過舊格式。

**阻擋**：🟡 Q8（重印 vs 重開）——編號格式可做，重開先只提供單一路徑

---

### Phase 5 — 機構核銷案

**表 — 新增**：`claim_batch_plans`（1:N，Q3）、`claim_documents`
**表 — 加欄位**：`claim_batches` 加 `void_reason`／`voided_at`／`voided_by`、status 擴充；`session_records` 加 `rejected_at`／`rejected_reason`

**依 Q1/Q2/Q3 的實作要點**：
- 子列表**可逐筆增減紀錄**（Q1），防漏／防重僅提示不阻擋
- **每月 1 號起可建案**，期間為參考區間，缺口／重疊**不硬檢查**（Q2）
- 一案**可跨方案**，但**先選方案再挑紀錄**（Q3）
- 鐘點費**可回溯修改**，寫 `audit_log`，**不重算酬勞**（Q4／Q22）

**頁**：`/claims` 重寫（4 分頁，**SelfPayTab 移除**）、心理師端 `/docs`（由 `DocConfirmTab` 搬出）

**`import_excel.py` 要跟著改**：無。舊資料無核銷案，`claim_batch_id` 本就留 `NULL`。但若 Phase 1 對既有 `type='self_pay'` 的 batch 做了封存遷移，需確認匯入腳本不會再產生該類型。

**阻擋**：無 ✅

---

### Phase 6 — 心理師端其餘頁面與酬勞

**表 — 新增**：`therapist_availability`
**表 — 加欄位**：`payout_details` 加 `amount`（可手動編輯）／`is_manually_adjusted`／`rate_changed_flag`

> `therapist_payouts` 拆五欄已在 **Phase 4** 完成，此處只用不改。

**Q23 實作**：採建議 a) — `commission_rate` × 有效金額為**預設值**，逐筆可手動覆寫，覆寫寫入 `audit_log`。

**頁**：`/today`、`/cases`(psy)、`/pay`（依賴 Phase 4 的 `/monthly`）

**`import_excel.py` 要跟著改**：無。酬勞不從 Excel 匯入。

**阻擋**：🟡 Q12（失約費計酬）／Q13（扣繳顯示）先用預設值；⛔ `lecture_fee`／`supervision_income`／`venue_deduction` 三欄**先建欄位但不填值**，等 Q16／Q17

---

### Phase 7 — 分析與報表

**表**：無（純讀取層）
**頁**：`/reports` → `/analytics` 改寫、心理師端 `/stats`

**`import_excel.py` 要跟著改**：無。

**阻擋**：🟡 Q18／Q19 與留案率算法先用預設值＋UI 標注

---

### Phase 8 — 講座／活動／場地租借（本輪排除）

**阻擋**：⛔ Q16／Q17 未定，見 §3.4

---

## 5. 開工前仍需回覆

只剩一題，且**不阻擋任何模組的結構開發**：

**Q6 — 15-45 青壯方案的個案自付額是 $0 還是 $400？**
心智圖內文說「機構全額」（＝$0），但心智圖自己的合約表與原型 seed 資料都寫 $400。只影響 seed 與收據名目，可先建表、標 `TODO(open_questions#Q6)`。

其餘 🟡 項目（Q7–Q21、Q23）已在 §3.3 給定預設值，實作時標註即可，不需停下來等。
