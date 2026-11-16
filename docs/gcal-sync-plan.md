# Cheerpsy Google 日曆同步與預約備註 — 實作計畫

文件日期：2026-11-16（Asia/Taipei）  
定位更新（2026-11-17）：本系統管理預約、媒合、診間／場地空間與行事曆，並詳細呈現金額與經費來源；**不對金流負責**（收款、對帳在行政另一套系統）。標題金額格式、收款記錄與失約費建議停用，見 §8.1 與文末實作記錄。  
對象：Cheerpsy（心理治療診所系統；FastAPI + SQLAlchemy + PostgreSQL + Alembic；Next.js `apps/web`）  
現況 Alembic head（疊加 PR 全部合併後）：`zi9e3f4a5b6e`（rooms 的 `is_active` / `sort_order`）  
既有能力：每位心理師一份 iCal 訂閱（`events.py`，路徑待確認），標題已去識別化（如「諮商 · 2B」），`cancelled` / `no_show` 以 `STATUS:CANCELLED` 保留 90 天。預約狀態：`booked`、`executed`、`cancelled`、`no_show`；只有 `booked`、`executed` 佔用診間。心理師不得看到其他心理師的個案。已有 `GET /rooms/occupancy`，只回 `{room_id, start, end, occupied}`。

本計畫只新增、不刪表、不改既有欄位語意。檔案路徑若未在本機核對過，以「例如」或「待確認」標示，實作前先對一次 repo。

---

## 0. 沙盒實測結論（2026-11-16）

用診所測試用 Gmail 實際跑過 `apps/api/scripts/gcal_sandbox.py`（分支 `chore/gcal-sandbox`，獨立腳本，不接進系統）。結論如下，下方各節已依此修正：

1. **Scope 組合可行**：`calendar.app.created` + `calendar.acls` 足以完成 `calendars.insert`、`events.insert／update／patch／delete／list`、`acl.insert／patch／delete／list`。**不需要退回較寬的 `calendar`。**
2. **`calendarList.list` 回 403**：此 scope 組合列不出日曆清單，所以 Cheerpsy 必須**自己記住每本日曆的 id**（`google_calendars` 表），不能靠列舉找回；日曆被誤刪時也只能以「`calendars.get` 回 404」偵測。
3. **`acl.list` 會包含擁有者**（診所帳號本人，以及日曆本身的 owner 項目）。計算分享名單時一律排除 `role=owner`。
4. **事件 id 可由預約 id 決定**（自訂 id 只能用 `a-v`、`0-9`，例如 `gcsb` + 5 位數）。重複同步結果相同，不會產生重複行程；曾刪除的同 id 事件再 insert 會回 409，改用 `events.update` 即可復活。
5. **`acl.insert` 預設會寄分享信**（`sendNotifications=true`），每新增一次 rule 就寄一次。同步時只對「差集」寫入，不要每次都重建 rule。
6. **分享不會自動出現在對方的日曆清單**，對方要點信裡的「加入日曆」。
7. 沙盒停在 Testing 狀態可驗證，但 **Testing 的 refresh token 只有 7 天**；正式上線前必須 Publish 到 Production（見 §9）。

---

## 1. 已定案的產品決策

1. **授權模型**：診所自有一顆個人 Gmail，由管理員在 Cheerpsy 做一次 OAuth。Google Cloud 專案 User type = External，Publishing status 改為 In production（可先不送 verification），以避開 Testing 模式 refresh token 7 天過期。  **正式上線前必須完成 Publish 到 Production，否則 refresh token 每 7 天失效**（沙盒在 Testing 驗證時親自確認過這個限制）。
   依據：[OAuth 2.0 refresh token expiration](https://developers.google.com/identity/protocols/oauth2)、[Manage App Audience](https://support.google.com/cloud/answer/15549945)、[Google Ads API common errors](https://developers.google.com/google-ads/api/docs/common-errors)、[When is verification not needed（個人／少於 100 位使用者）](https://support.google.com/cloud/answer/13464323)、[OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)。
2. **Scope**：先請求 `https://www.googleapis.com/auth/calendar.app.created` 與 `https://www.googleapis.com/auth/calendar.acls`。前者可建次要日曆並在其上寫事件（[calendars.insert](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert)、[events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)）；後者才能設 ACL（[acl.insert 只接受 `calendar` 或 `calendar.acls`](https://developers.google.com/workspace/calendar/api/v3/reference/acl/insert)）。此組合已在沙盒實測可行（見 §0），**不採用較寬的 `calendar` scope**。
3. **日曆結構**：**每位心理師一本日曆，不做總表。** 日曆名稱「[SANDBOX] Cheerpsy · 名字」在正式環境改為「Cheerpsy · 名字」。診所 Gmail 是**全部日曆的擁有者**，每本日曆只放該心理師自己的場次。分享規則（reader 權限、`sendNotifications=true`）：
   - 分享名單 = **該心理師本人的 Gmail（僅在職時）∪ 行政人員 Gmail 清單**，以集合聯集計算、去重。
   - **擁有者不分享**：名單裡若出現診所帳號本人，直接略過（輸出註明「已是擁有者」，驗證視為合法）。
   - **同一人兼心理師與行政時，ACL 只有一筆 rule**（聯集去重）。移除其中一個身分（例如行政名單拿掉他），只在「聯集裡已沒有他」時才刪 rule，**不會誤刪**仍屬於另一個身分的分享。
   - 同步以「目標名單 vs `acl.list` 實際內容」的差集為準：缺的 `insert`、多的 `delete`，權限不是 reader 的改成 reader。
   - **離職**：取消分享給他本人、停止推送（事件凍結不再更新）、**日曆本體不刪**；行政仍看得到。凍結期間唯一的例外是隱私清理：若日曆裡出現不屬於他的場次（例如場次已改派他人），仍會移除。
   依據：[Calendar sharing](https://developers.google.com/workspace/calendar/api/concepts/sharing)、[Subscribe to someone else’s calendar](https://support.google.com/calendar/answer/37100)。  
   官方註明：分享後**不會**自動插入對方的 `CalendarList`，Cheerpsy 也沒有心理師本人的 OAuth，因此無法代為 `CalendarList.insert`；務必依賴通知信，並在畫面上寫清楚操作步驟。
4. **不做診間總表**：沙盒結論是每位心理師一本日曆已足夠；診間佔用只在 Cheerpsy 預約介面以「已佔用」遮蔽顯示（對齊 `/rooms/occupancy`），**不推到 Google**。
5. **同步方向**：只從 Cheerpsy 推到 Google。Cheerpsy 是唯一資料來源。若有人在 Google 上改了行程，下一次推送會蓋回去（不做 Google → Cheerpsy 回寫）。
6. **事件標題格式是診所設定**，四選一（**預設 (d)**，診所 2026-11-16 後續決定；(a)(b)(c) 保留較保守的選項）。事件內容規則以 §5 為準（標題可含個案全名與個案這次要付的金額、描述只含備註；電話、Email、主訴仍不放）：  
   - (a) 只顯示類型與診間，例如「諮商 · 2B」；線上場次顯示「線上」。  
   - (b) 再加上個案代號，例如「諮商 · 2B · C-1042」。  
   - (d) 類型 · 診間 · 個案全名（**預設**，例如「諮商 · 2B · 陳小美」）。
   - (c) 再加上姓名縮寫（規則見下）：三字名取前兩字（陳小美→「陳小」）、複姓取三字（歐陽小明→「歐陽小」）、兩字名只顯示姓（王明→「王」）；單字或無法拆解時退化成 (a)。(a)(b)(c) **不輸出完整姓名**，只有 (d) 會；iCal 預設仍維持目前去識別化，除非診所另外決定要對齊。
   **金額**（2026-11-17 改）：標題結尾加「 · $…」。自費「$全額」；機構「$總額（自付 $X）」，全額補助「$總額（機構全額）」，自付額未知（NULL）「$總額（自付未設定）」；總額 0 不顯示；**描述不放金額**。金額必須大於 0（借場地方案例外）。**預約備註**放在描述，分段標示。絕不把電話、Email、主訴／病歷內容寫進 Google 事件。
7. **既有 iCal 訂閱保留**，作為不需 OAuth、更新較慢的備援。
8. **預約備註給心理師**：行政／管理員可在特定預約上寫「備註給心理師」。只有該預約的負責心理師、以及行政／管理員看得到；其他心理師看不到。預設不推到 Google（可另設開關，預設關閉）。
9. **遮蔽「已佔用」只存在於 Cheerpsy 預約介面**：Google 日曆**不顯示他人預約**——每位心理師的日曆只有自己的場次，行政人員的唯讀分享是同一批日曆（逐本檢視），不會有一本合併後的他人佔用視圖。

不在本階段：讀回心理師私人行程當「忙碌」、雙向同步、Workspace / 服務帳號 / domain-wide delegation、每位心理師各自 OAuth。

---

## 2. 架構

### 2.1 原則

同步不可阻塞預約 API。建立、改期、改房、取消、未到，應在同一交易裡寫入「待推送」紀錄後立刻回 2xx，由背景工作者再打 Google。Google 當下失敗不得讓預約寫入失敗。

官方建議對配額與暫時錯誤做截斷指數退避，並避免整點一次全量同步造成流量尖峰（[Usage limits](https://developers.google.com/workspace/calendar/api/guides/quota)、[Avoid Calendar use limits](https://knowledge.workspace.google.com/admin/calendar/avoid-calendar-use-limits)）。

### 2.2 元件（建議）

| 元件 | 責任 |
| --- | --- |
| 設定與 OAuth 路由 | 管理員連結／解除診所 Google；callback 換發並加密存放 refresh token |
| 日曆佈建與分享同步服務 | 為心理師建立次要日曆、依名冊與行政名單計算分享聯集並對 Google 做差集 insert／delete、離職取消分享並凍結 |
| 標題組裝函式 | 依設定與預約資料產出 summary／description；保證不含禁用欄位 |
| 領域事件掛鉤 | 在預約建立、批次、改期、改房、取消、未到、媒合轉初診成功後 enqueue（與現有 `assert_room_free` 等寫入路徑同一層，檔名待確認，例如 `appointments.py`、`referrals` 的 convert） |
| Outbox 表 + 工作者 | 可靠投遞、重試、冪等、指標（上次成功／失敗） |
| 備註模組 | 獨立於 Google；權限過濾；編輯歷程；可選已讀 |

工作者形態（待確認現有慣例）：優先獨立 process，例如 `python -m ...gcal_worker`，由既有 process 管理員（systemd / compose）一併啟動。若 repo 已有 APScheduler、ARQ 或類似機制則沿用，不要另開一套。單診所規模不需要外部 queue。

### 2.3 Outbox 與重試

流程：

1. 預約狀態變動 → 插入 `gcal_outbox`（`job_type=upsert_event | delete_event`，`appointment_id`，`dedupe_key`）。同一預約若已有 `pending`／`retry` 的相同 `job_type`，改更新該列（避免堆積）。改期後的正確動作是 upsert 同一 `google_event_id`，不是先刪再建（除非日曆變更，見下）。
2. 工作者每次取一批 `status in ('pending','retry') and next_attempt_at <= now()`，`FOR UPDATE SKIP LOCKED`，避免多實例搶同一筆。
3. 執行前再讀一次預約現況（避免 outbox 落後於後續修改）。規則：  
   - `booked`、`executed` → upsert（有 `google_event_id` 就 `events.patch`／`update`，沒有就 `events.insert`，成功後寫回 id）。  
   - `cancelled`、`no_show` → 刪除 Google 事件（房間已釋出，日曆上不應再佔時段）。若事件已不存在，視為成功。刪除後清空 `google_event_id`。  
   - 心理師未設定 Gmail、或診所尚未完成 OAuth、或該心理師日曆尚未建好 → 工作列標記 `blocked`，原因寫清楚，設定補齊後可一鍵重排隊。  
   - 改期若換了負責心理師（若系統允許；待確認）→ 從舊日曆刪除，在新日曆 insert，更新對應。
   - 心理師離職（名冊標為離職）→ 取消分享給他本人，該日曆事件**凍結**（停止 upsert／delete），日曆不刪；只清除不屬於他的場次。
4. 冪等：`appointment_google_events`（或等價表）存 `google_event_id`、`google_calendar_id`、以及上次推送內容的 hash（時間、診間、標題、狀態）。hash 相同則直接標 `done`，不打 API。
5. 錯誤處理：  
   - 429／403 usageLimits、5xx、暫時性網路錯誤 → 指數退避（1s、2s、4s… 加抖動，上限約 64s，之後固定間隔），參考[官方 backoff 寫法](https://developers.google.com/workspace/calendar/api/guides/quota)。`attempts` 累加，例如 10 次後改 `failed` 並發警報，管理員可手動重試。  
   - `invalid_grant`（token 撤銷或過期）→ 連線狀態改 `token_invalid`，暫停所有工作為 `blocked`，設定頁與（建議）站內橫幅提示管理員重新連結。[Refresh token 失效原因](https://developers.google.com/identity/protocols/oauth2)。  
   - 409／404 事件衝突或不存在 → 清掉本地 `google_event_id` 後改走 insert，或視為已刪除。  
   - 日曆被手動刪除 → 該心理師日曆狀態改 `missing`，提示重建。
6. 分享名單同步：名冊（心理師 Gmail、在職狀態）或行政名單變動時 enqueue `share_acl`／`unshare_acl`；一律先算目標聯集（排除擁有者）再與 `acl.list` 比對，只寫差集，避免重複寄分享信。
7. 「全部重新同步」：管理員按鈕對所有 `booked`／`executed`（及設定所涵蓋的未來／近期區間，建議預設「過去 30 天至未來 180 天」，可調） enqueue upsert；對已不該存在於 Google 的對應事件 enqueue delete。必須限流，分散流量，不可一次打爆單一日曆（官方提醒不要對單一日曆密集寫入）。

Google 編輯的覆蓋策略：Cheerpsy 不訂閱 push notification，也不定期 pull 比對（可列為後續選項）。只要 Cheerpsy 端再有變更或有人按重新同步，就以 Cheerpsy 為準覆寫。畫面上用一句話告知：請勿在 Google 上改 Cheerpsy 行程，改了會被蓋掉。

### 2.4 與 iCal 的關係

iCal 產生邏輯獨立，繼續服務未使用 Google、或尚未點加入的心理師。標題函式可抽共用，但 iCal 預設維持現況（類型 · 診間），避免已訂閱的隱私承諾被設定項悄悄加嚴／放寬。若診所希望兩者一致，再加「iCal 跟隨標題格式」設定，預設關閉。

---

## 3. 資料模型與 Migration

全部新增。Alembic revision 接在 `zi9e3f4a5b6e` 後面。建議拆兩支（可依 PR 再切）：

- `zj0f4a5b6c7d_gcal_and_settings`（OAuth、日曆對應、outbox、診所設定）
- `zk1a5b6c7d8e_appointment_notes`（備註與歷程）

downgrade 只 drop 本支新增的表／欄／索引，不碰既有表。model 的 `__table_args__` 與 migration 一致，讓 `create_all` 的測試也建得到。

### 3.1 診所設定 `clinic_settings`（單列或多鍵值；建議單列以免滿天鍵）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | 整數 PK | 固定只有一列（check 或 application 保證） |
| `event_title_format` | enum / text | `type_room`（a）、`type_room_code`（b）、`type_room_abbrev`（c）、`type_room_name`（d），**預設 `type_room_name`（d）**（診所已決定；migration `zm3c7d8e9f0a`） |
| `staff_share_emails` | text[] / json | 行政人員 Gmail 清單；每本日曆都以 reader 分享給名單上的人（診所帳號本人除外）。預設空 |
| `push_therapist_notes_to_google` | boolean | 預設 false；本階段即使得 true，也只推備註本文、仍禁止聯絡資料 |
| `ical_follow_title_format` | boolean | 預設 false（建議項） |
| `resync_lookback_days` | int | 預設 30 |
| `resync_lookahead_days` | int | 預設 180 |
| `updated_at` / `updated_by_user_id` |  |  |

其他建議設定見 §7.3，若本階段要做，加在同一表，標為選做欄位。

### 3.2 Google 連線 `google_oauth_connections`（預期 0 或 1 列）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | PK |  |
| `google_email` | text | 授權成功後向 Google 讀回的帳號 |
| `refresh_token_enc` | bytea / text | 用環境變數金鑰加密後的 refresh token，**絕不寫入 log** |
| `scopes` | text | 實際授權到的 scope，空白分隔 |
| `status` | text | `active` / `token_invalid` / `disconnected` |
| `token_invalid_at` | timestamptz |  |
| `last_success_at` | timestamptz | 任一成功的 API 呼叫 |
| `last_error_code` / `last_error_message` | text | 給設定頁看的摘要，不得含 token |
| `connected_by_user_id` | FK users |  |
| `connected_at` / `updated_at` |  |  |

Access token 不必持久化（短效，用時刷新即可）。Client ID / Secret 走環境變數，不進資料庫。

### 3.3 日曆對應 `google_calendars`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | PK |  |
| `therapist_id` | FK | 唯一：每位心理師一本日曆 |
| `google_calendar_id` | text | Google 回傳的 calendar id |
| `summary` | text | 例如「王心理師 · Cheerpsy」 |
| `shared_emails` | text[] / json | 上次同步完成後的分享名單快照（只給畫面顯示；實際以 Google `acl.list` 為準） |
| `share_status` | text | `not_shared` / `invited` / `unshared` / `error`（無法可靠偵測對方是否已點加入，只記「已送出 ACL」） |
| `last_share_error` | text |  |
| `is_active` | boolean | 停用後不再推送 |
| `created_at` / `updated_at` |  |  |


心理師 Gmail 建議存在既有使用者／心理師檔（欄位名待確認）。若使用者表沒有合適欄位，本 migration 新增 `users.gcal_share_email`（或 `therapists.gcal_share_email`）——**只加欄、不改既有欄**。行政為心理師填寫並觸發分享。

### 3.4 事件對應 `appointment_google_events`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `appointment_id` | FK PK | 一對一 |
| `google_calendar_id` | text |  |
| `google_event_id` | text |  |
| `payload_hash` | text |  |
| `last_pushed_at` | timestamptz |  |
| `last_status` | text |  |

### 3.5 Outbox `gcal_outbox`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | PK |  |
| `job_type` | text | `upsert_event` / `delete_event` / `ensure_calendar` / `share_acl` / `unshare_acl` / `resync_batch` |
| `appointment_id` | FK nullable |  |
| `therapist_id` | FK nullable | 佈建／分享用 |
| `dedupe_key` | text unique | 例如 `upsert:{appointment_id}` |
| `status` | text | `pending` / `retry` / `blocked` / `done` / `failed` |
| `attempts` | int | 預設 0 |
| `next_attempt_at` | timestamptz |  |
| `last_error` | text |  |
| `created_at` / `updated_at` / `finished_at` |  |  |

索引：`(status, next_attempt_at)`、`appointment_id`。

### 3.6 預約備註

建議獨立表，不用預約表加一欄，以便歷程與已讀。

`appointment_notes`（每個預約至多一筆「給心理師的備註」；更新時寫歷程。若實務上需要多則對話，第一版仍先採「單筆可編輯」，較好做已讀與權限）：

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | PK |  |
| `appointment_id` | FK unique |  |
| `body` | text | 純文字；長度上限建議 2,000 字 |
| `created_by_user_id` / `updated_by_user_id` | FK |  |
| `created_at` / `updated_at` |  |  |
| `read_at` | timestamptz nullable | 負責心理師首次展開／標記已讀 |
| `read_by_user_id` | FK nullable |  |

`appointment_note_revisions`：

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | PK |  |
| `note_id` | FK |  |
| `body` | text | 編輯前的內容 |
| `edited_by_user_id` | FK |  |
| `edited_at` | timestamptz |  |

刪除備註：軟刪（`deleted_at`）或寫一筆空本文＋歷程；不要硬刪歷程。建議軟刪，心理師端不再顯示，行政仍可在歷程看到。

既有稽核表（若有，路徑待確認）每筆新增／編輯／刪除／已讀都寫一筆，含 `appointment_id`、操作者、不含其他個案欄位以外的多餘 PHI。若沒有通用稽核表，備註歷程表即為最小稽核來源，另在應用 log 記 `user_id + appointment_id + action`（不記本文）。

---

## 4. Token 與機密存放

- 環境變數（名稱待確認，建議）：`GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET`、`GOOGLE_OAUTH_REDIRECT_URI`、`GCAL_TOKEN_FERNET_KEY`（或 AES-GCM key）。金鑰遺失即無法解密，須重新授權，故要備份在診所的密碼管理工具，不進 git。
- Refresh token 入庫前加密，讀出時解密，只用在 Google token endpoint。Log、錯誤訊息、API 回應、前端都不得出現 token 或 authorization code。
- 解除連結：撤銷 Google token（若 API 呼叫失敗仍繼續本地清除）、刪除密文、`status=disconnected`，停止工作者。既有 `google_calendars` 列保留但 `is_active=false`，方便日後重連後對到同一個 calendar id（若日曆還在）。
- 診所那顆 Gmail 必須開兩步驟驗證，權限集中保管。本系統不存該帳號密碼。

---

## 5. 隱私規則與事件內容

強制規則（測試要鎖死）：

- Google 事件**從不**包含電話、Email、地址、主訴／病歷／治療備註、帳務備註、機構。**完整姓名只出現在標題格式 (d)**（預設，診所決定）。**金額**（個案這次要付的錢：機構案＝自付額，自費案＝`amount`）只出現在標題結尾，描述不放；0 元不顯示。應收總額、方案、額度、收款狀態不推到 Google。
- 描述的備註分段：「預約備註」（預約上目前**沒有**備註欄位，尚無可放；若日後新增，在 `gcal_push.note_sections` 加一段）與 PR D 的「備註給心理師」（做好後在同一處加一段「備註給心理師」；是否推送仍受 `push_therapist_notes_to_google` 控制）。各段以「【標題】」分隔，空內文不輸出。備註或金額改變 → 事件內容 hash 變 → 重新同步；寫備註的路徑要自行呼叫 `enqueue_appointments`（金額在 `WATCHED` 欄位裡，自動入列）。
- 標題依 `event_title_format`：  
  - (a) `{類型} · {診間代號}`；無診間的線上／外展：`{類型} · 線上` 或 `{類型} · 外展`（對齊既有場次類型欄位，待確認欄位名）。所有格式有金額時結尾再加 ` · $1,500`。
  - (d)（預設）在 (a) 後追加個案全名：`諮商 · 2B · 陳小美`。  
  - (b) 在 (a) 後追加 ` · {個案代號}`（代號欄位待確認；沒有代號就退化成 (a)，不可改塞姓名）。  
  - (c) 在 (a) 後追加姓名縮寫（沙盒實測規則，實作寫成純函式並補單元測試）：中文姓名——三字名取**前兩字**（陳小美→「陳小」）；**複姓取三字**（歐陽小明→「歐陽小」，複姓清單：歐陽、司馬、諸葛、上官、夏侯、皇甫、尉遲、公孫、慕容、令狐、長孫、宇文）；**兩字名只顯示姓**（王明→「王」，因為姓＋名的第一字會等於全名）；單字或無法拆解→退化成 (a)。非中文姓名：`Given-name + surname initial`（`Mei Chen` → `Mei C.`），只有一個字則退化成 (a)。不確定時寧可退化成 (a)，不可輸出完整姓名。
- `description`：固定句「由 Cheerpsy 同步，請勿在此修改。」＋備註分段；不放金額、電話、Email、主訴。
- 心理師日曆名稱可用心理師顯示名稱（不是個案）。
- 佔用隱私與 `/rooms/occupancy` 一致：他人場次只在 Cheerpsy 預約介面顯示「已佔用」；**Google 日曆不顯示他人預約**，每本日曆只含該心理師自己的場次。
- API 與前端：心理師查備註、預約詳情時，後端以「該預約的 `therapist_id` == 目前使用者」過濾；禁止用客戶端傳來的 therapist id 放寬。其他心理師的預約詳情、備註、個案代號與縮寫來源資料一律 404（不要 403，避免探測）。
- iCal 維持現況去識別化，除非開啟跟隨設定。

---

## 6. API（建議路徑，實作前對齊現有 router 風格）

認證皆需登入。角色見 §8。核銷、對帳、流水不在本範圍；金流資訊（機構方案、額度、收款記錄）保留，權限見 §8.1。錯誤：未登入 401；角色不符 403；Google 未連結而要執行推送／分享時 409，訊息說明要先連結。

### 6.1 設定與 OAuth（僅 admin，除特別註明）

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/settings/clinic` | 回傳標題格式、行政分享名單、備註是否推 Google、同步健康狀態（連線 email、status、last_success_at、last_error、pending/failed outbox 數、token 無效旗標）。staff 可讀健康狀態與自己需要的子集，見權限表。 |
| PATCH | `/settings/clinic` | 改設定。改標題格式不立刻全量重推，畫面提示可按「全部重新同步」。 |
| GET | `/settings/google/connect` 或 POST 回 `{authorization_url}` | 開始 OAuth（`access_type=offline`、`prompt=consent`，確保拿到 refresh token）。 |
| GET | `/settings/google/callback` | Google 導回；驗證 state；換 token；寫入加密 refresh token；導回前端設定頁。此 callback 需列入 Google Cloud 的 Authorized redirect URI。 |
| POST | `/settings/google/disconnect` | 解除連結。 |
| POST | `/settings/google/resync` | 全部重新同步（enqueue，立刻回 202）。 |
| POST | `/settings/google/retry-failed` | 把 `failed`／`blocked`（在條件允許時）改回 pending。 |

### 6.2 心理師日曆對應（admin 全開；staff 可寫 Gmail 並觸發分享）

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/settings/google/therapists` | 每位心理師：姓名、id、share_email、日曆是否已建、share_status、最後錯誤。不含個案。 |
| PUT | `/settings/google/therapists/{id}/email` | 設定／更改分享用 Gmail。若已分享給舊信箱，enqueue 先 unshare 再 share 新地址。 |
| POST | `/settings/google/therapists/{id}/provision` | 建立次要日曆（若尚未建立）並分享。短時間批次建立時需自我節流（官方：短時間不要建立超過 60 個日曆，見 [Avoid Calendar use limits](https://knowledge.workspace.google.com/admin/calendar/avoid-calendar-use-limits)）。 |
| POST | `/settings/google/therapists/{id}/resend-invite` | 重送分享（必要時先刪舊 ACL 再建，`sendNotifications=true`）。 |
| POST | `/settings/google/therapists/{id}/unshare` | 移除 ACL（離職）。日曆保留、停止推送可另設 `is_active=false`。 |

行政分享名單：`GET／PUT /settings/google/staff-emails`（admin 才能改；staff 唯讀）。變更後 enqueue 對所有日曆的 `share_acl`／`unshare_acl`，一律以「心理師 Gmail ∪ 行政名單 − 擁有者」的差集計算。

### 6.3 備註

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/appointments/{id}/therapist-note` | 權限見 §8。無備註回 `null`。含 `read_at`、更新時間、作者顯示名。歷程另見下。 |
| PUT | `/appointments/{id}/therapist-note` | staff/admin 建立或更新；更新前把舊本文寫入 revisions。空字串視為刪除（軟刪）。 |
| GET | `/appointments/{id}/therapist-note/revisions` | staff/admin；心理師預設看不到歷程（建議，減少干擾）。 |
| POST | `/appointments/{id}/therapist-note/read` | 僅該預約負責心理師；設 `read_at`（已有則冪等）。亦可在 GET 詳情時自動標記，但「自動已讀」要在計畫裡做成選項，預設改為：心理師打開預約詳情且備註區塊有渲染時才自動已讀，避免列表預覽誤標。 |

列表提示：`GET /appointments`（以及心理師今日／班表用的既有列表 endpoint，待確認）可加非敏感旗標 `has_therapist_note`、`therapist_note_unread`（只對有權限的人出現；其他心理師的回應不得帶這些旗標）。

---

## 7. 前端頁面與操作

路徑待確認：設定可放在既有 `/admin` 新分頁，或新頁 `/settings`。心理師看不到診所 Google 連線與他人對應表。

### 7.1 管理員：診所設定與 Google（必做）

單一「日曆與同步」畫面，區塊如下：

1. **Google 連線**：未連結顯示「連結診所 Google 帳號」按鈕與簡短說明（會開 OAuth、只管理 Cheerpsy 建立的日曆、不會讀私人行事曆——若最後 scope 退回 `calendar`，文案必須改成如實披露）。已連結顯示 Google email、狀態（正常／Token 失效／已解除）、最後成功時間、未完成／失敗工作數。Token 失效用明顯警告：「同步已暫停，請重新連結」。提供解除連結（二次確認）。
2. **事件標題格式**：三個選項加範例預覽（同一筆假資料切換 a/b/c）。說明「不會把完整姓名、備註、聯絡方式寫進 Google」。
3. **行政分享名單**：列出目前行政 Gmail、可增減；說明「名單上的人會以唯讀權限看到每位心理師的日曆，診所帳號本人不需列入」。變更後顯示各日曆分享同步狀態。
4. **備註是否同步到 Google**：預設關，並警告開啟後備註會離開本機系統、進到 Google。
5. **全部重新同步**、**重試失敗工作**。按鈕需確認，完成後顯示「已加入佇列」。
6. **心理師對應表**（表格）：心理師、分享用 Gmail、日曆狀態、邀請狀態、操作（儲存信箱、建立並分享、重寄邀請、取消分享）。列出示範給心理師的說明文字，可複製：「你會收到 Google 的分享信，請在電腦版開啟並點加入日曆；之後場次會自動出現。請勿在這個日曆上改時間。」

### 7.2 行政人員（必做）

Staff **不必**連結／解除 Google、不必改標題格式與行政分享名單、不必按「全部重新同步」（避免誤觸；必要時可由管理員做）。Staff **可以**：

- 查看同步是否正常（只讀狀態；token 失效時看到「請通知管理員重新連結」）。
- 為心理師填寫／修改 Gmail，並觸發「建立並分享」或「重寄邀請」「取消分享」。
- 在預約上寫備註給心理師（§7.4）。

### 7.3 其他診所設定（建議，非本階段必做）

可放在同一設定頁的「預約預設」區塊，實作時可另開小 PR：

| 建議項 | 為什麼有用 | 優先 |
| --- | --- | --- |
| 預設場次長度（依類型：諮商 50／60、遊戲治療…） | 行政從日曆點空白格進預約時少填一次 | 高 |
| 預約提醒文案（簡訊／Email 範本，若已有通知機制） | 統一口吻；不含過度 PHI | 中（沒有通知系統就先不做） |
| 線上／外展的顯示名稱 | 標題「線上」用字統一 | 低 |
| iCal 是否跟隨標題格式 | 讓兩種日曆一致 | 低 |
| 重新同步的時間窗 | 避免一次掃到過舊歷史 | 低 |

不要在本階段做完整通知中心、權限矩陣 UI、或心理師自己改分享信箱（信箱由行政統一填，避免填錯）。

### 7.4 備註給心理師（必做）的畫面位置

- **`/appts`**：列上未讀／有備註標記；點進去的詳情（或側欄）有「備註給心理師」區塊。staff/admin 可編輯；該預約心理師只讀，可看見已讀狀態。
- **`/calendar` 詳情**：行政點自己權限內的預約，同上。心理師點自己的場次才看得到備註；「已佔用」遮罩格仍不可點、不可讀備註。
- **心理師 `/today` 與班表**：自己的場次若有未讀備註，清楚標記；點開可見全文，打開後標已讀。
- 編輯框提示：這則備註只有本預約的心理師與行政／管理員看得到，預設不會進 Google 日曆。
- staff/admin 可展開編輯歷程。心理師預設不展開歷程。

---

## 8. 角色權限矩陣

### 8.0 核心原則（不得再誤解）

**隔離的單位是「心理師」，不是「欄位」。** 心理師對**自己**的個案與預約擁有完整權限，**包含金額**、時間、診間、狀態：可看、可建立、可修改；金額由心理師自己填，表單必須顯示，API 回真實金額（不可回 0、不可忽略心理師送的值）。同時，心理師完全看不到、碰不到**其他心理師**的預約、個案、金額：

- 別人的預約／個案，讀、改、取消、刪除一律 **404**，且與「id 根本不存在」的回應完全相同（不可用猜 id 推測存在）；列表與批次端點不混入別人的資料。
- **刪除預約只限 admin／staff。** 心理師呼叫單筆（`DELETE /appointments`）或整批（`DELETE /appointments/batch`）刪除，自己的預約一律 **403**，別人的仍是 **404**；心理師只能「取消」自己的預約（`PUT /appointments/{id}/cancel`）。前端本來就沒有預約刪除按鈕，之後新增時也不得對心理師顯示。
- 心理師可改自己個案的資料，但**不能改派、不能改個案狀態**（403）。
- 不能把預約改派給別人（更新沒有負責心理師欄位），不能用別人的個案（含伴侶案）建立預約；也不能把自己的個案改派或自行改個案狀態。
- 預約與診間介面中，別人佔用的時段只顯示「已佔用」（`/rooms/occupancy`），不含姓名、金額、心理師。
- Google 日曆只有該心理師自己那一本，只含自己的預約；改金額會觸發重新同步，且只推到該心理師的日曆。
- **禁止**用「依角色隱藏或歸零某個欄位」的方式做隔離；權限一律以「擁有者」判斷（`therapist_id == 登入者`）。
- staff：可看可改所有心理師的個案、預約、金額，可管理日曆分享（不能改 OAuth 連線）。admin：staff 全部加設定、OAuth、診間管理、全部重新同步。accountant：記帳已移除，維持現狀（不能建立預約，金額一律 0）。


accountant 角色仍存在，本功能預設**不開放**（與帳務脫鉤後不必給日曆設定或備註）。若實務上會計也做行政，再另議。

| 能力 | admin | staff | therapist（自己的預約） | therapist（他人預約） | accountant |
| --- | --- | --- | --- | --- | --- |
| 連結／解除診所 Google、改標題格式、行政分享名單、備註推送開關、全部重同步 | 是 | 否 | 否 | 否 | 否 |
| 讀取同步健康狀態 | 是 | 是（只讀） | 否 | 否 | 否 |
| 為心理師設定 Gmail、建立日曆、重寄邀請、取消分享 | 是 | 是 | 否 | 否 | 否 |
| 建立／編輯／軟刪「備註給心理師」 | 是 | 是 | 否 | 否 | 否 |
| 讀取該預約備註 | 是 | 是 | 是 | 否（404） | 否 |
| 讀取備註編輯歷程 | 是 | 是 | 否（建議） | 否 | 否 |
| 標記已讀 | 否 | 否 | 是 | 否 | 否 |
| 看到列表上的未讀旗標 | 是 | 是 | 僅自己的場次 | 否 | 否 |
| 既有日曆佔用（已佔用、occupancy） | 既有規則 | 既有規則 | 既有規則 | 只見佔用、無個案 | 既有規則 |

後端強制以上規則，前端只是隱藏按鈕。

### 8.1 金流資訊（方案、額度、金額呈現）

本系統不負責收款與對帳（在行政另一套系統）；核銷、對帳、流水已移除，收款記錄與失約費建議已停用（端點回 410、欄位保留）。以下是保留的呈現與維護，**隔離單位仍是心理師**。

| 能力 | admin | staff | therapist（自己的個案／預約） | therapist（他人） | accountant |
| --- | --- | --- | --- | --- | --- |
| 機構、合約、方案、價目、交通費（讀寫） | 是（刪方案僅 admin） | 是（不含刪方案） | 否 | 否 | 讀（無寫入） |
| 個案額度（總堂數／已用／剩餘）建立、調整 | 是 | 是 | 唯讀自己個案 | 否（404） | 否 |
| 預約帶方案、總額、自付額、機構補助（算出）、交通費 | 是，可手動調整（稽核；金額須 > 0） | 是 | 可建立；看得到真實金額與方案 | 否（404） | 否 |
| ~~記錄收款、失約費建議~~ | 已停用 | 已停用 | 已停用 | — | — |

額度不足**不擋預約**：照常建立，回應 `warnings`，前端提示。無 master 日曆：Google 端仍是每位心理師一本。

---

## 9. Google Cloud 設定步驟（給實作者／管理員）

在瀏覽器以診所要用來開專案的 Google 帳號操作（建議與診所日曆 Gmail 是同一人或可信託管）：

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 新建專案，例如「Cheerpsy Calendar」。
2. 啟用 [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)。
3. 設定 OAuth 同意畫面（現為 Google Auth Platform）：User type 選 **External**。填應用程式名稱、支援 Email、開發者聯絡 Email。要發到 Production 前，首頁、隱私權政策、服務條款連結與 Authorized domain 依 [Branding 說明](https://support.google.com/cloud/answer/10311615) 備妥（External production 需要這些連結）。隱私權政策須說明：只為同步診所建立的次要日曆與事件、不把個案聯絡資料寫入日曆。
4. Data Access 加入 §1 的 scope。分類（sensitive / restricted）以 Console 顯示為準；官方把「讀取 Calendar 行程」列為 sensitive 的例子（[Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)）。公開文件未逐條標示本計畫採用的 scope 是否 restricted，不要自行假設。
5. **Publish app**，使 Publishing status 成為 In production。這一步**不是**送出 verification。未驗證的 External 應用在敏感 scope 會顯示未驗證警告，且有終身 100 位新使用者上限（[Unverified apps](https://support.google.com/cloud/answer/7454865)、[app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)）。本系統只有診所一顆 Gmail 授權，遠低於此上限。管理員連結時會看到警告，需點繼續。 **這是正式上線前的必做項目**：沙盒停在 Testing 時 refresh token 只有 7 天，Publish 之後才不會每週要重新授權。
6. 建立 OAuth Client ID，類型 **Web application**（本機沙盒腳本用的是 Desktop app，兩者不同，不要共用）。Authorized redirect URI 必須與後端 callback **完全一致**（本機與正式環境各一條，例如 `http://localhost:8000/.../callback` 與正式 HTTPS URI，實際路徑待確認）。
7. 把 Client ID、Secret、Redirect URI、Fernet 金鑰放入伺服器環境變數，不要提交進 repo。
8. 在 Cheerpsy 用**診所日曆那顆 Gmail**登入授權（先加入測試使用者不是必須，因為已 Publish；若仍暫留 Testing，則必須把該 Gmail 加成 test user，且 token 會 7 天過期——正式使用不要停在 Testing）。
9. 授權後再為心理師建立日曆與分享，不要反過來。

送 Google verification 非本階段必需（[個人使用例外](https://support.google.com/cloud/answer/13464323)）。若未來要給許多外部使用者各自授權，再準備示範影片、網域驗證與較長審核期。

---

## 10. 維運手冊

| 情況 | 處理 |
| --- | --- |
| Token 失效（管理員撤銷權限、改密碼後的特定情況、Testing 殘留、超過 6 個月未使用等，見[官方列表](https://developers.google.com/identity/protocols/oauth2)） | 設定頁警告；outbox 轉 `blocked`；管理員重新連結。連結成功後按「重試失敗工作」或「全部重新同步」。**Publish 之後取得的 token 不會僅因 7 天而過期**；若仍 7 天一斷，先確認同意畫面不是 Testing，且重新授權是在 Publish **之後**。 |
| 心理師沒收到分享信 | 請檢查垃圾信、是否用電腦版日曆開啟（[官方：須用電腦瀏覽器訂閱](https://support.google.com/calendar/answer/37100)）。按「重寄邀請」。確認 Gmail 拼寫。 |
| 心理師已點加入但仍沒行程 | 看該列日曆是否已建、outbox 是否 failed、該預約是否為 booked/executed。可對單一心理師 enqueue 重推（建議在對應表加「重推此人」，第一版也可用全量重同步）。 |
| 心理師離職 | 名冊標為離職後執行同步：取消分享給他本人、事件凍結、日曆不刪（行政仍看得到，保留稽核與復原）。復職時改回在職再同步，會重新分享並恢復推送。不要刪 migration／資料列；日曆本體是否在 Google 端刪除，由管理員人工決定。 |
| 心理師更換 Gmail | 先 unshare 舊址、再 share 新址；重寄邀請。 |
| 有人在 Google 改了時間 | 系統不自動發現。下次該筆有變更或重同步時會被 Cheerpsy 覆寫。教育使用者在 Cheerpsy 改期。 |
| 診所 Google 日曆被誤刪 | 對應表標 missing；「重建日曆並重推」。 |
| 短時間大量新建日曆被擋 | 遵守約 60 個／短時間的指引，分批 provision。 |
| 部署 | 工作者 process 要與 API 一起起來；migration 先於流量。環境變數缺失時 API 可啟動，但連線按鈕回 503／明確錯誤，避免靜默失敗。 |

---

## 11. 測試計畫

原則：**測試不打真實 Google、不走外網**。抽一層 Calendar client（protocol / protocol interface），測試注入 fake。另備很小的手動腳本（不進 CI）給開發者用測試專案實打。

必測（pytest + 前端 tsc / lint；新頁面建議加元件測試若專案已有慣例）：

**OAuth 與設定**

- 未登入 401；staff 不能 connect／disconnect／resync／改標題格式。
- callback 成功時 refresh token 以密文入庫，API 回應與 log 不含密文。
- disconnect 後 status 正確、後續 enqueue 的工作進入 `blocked`。

**標題與隱私**

- a/b/c 三種格式的純函式測試，含線上、缺診間、缺代號、中文姓名拆解、無法拆解時不輸出全名。
- upsert 送到 fake client 的 payload 不得出現全名、電話、Email、備註本文（開關關閉時）。

**Outbox 與冪等**

- 建立預約 → 一筆 upsert；改期／改房 → 仍對同一 `google_event_id` 做 update，且時間／標題有變。
- 取消、未到 → delete；事件已不存在視為成功。
- 同一預約連續兩次改期只保留／合併 pending，不重複插入多筆成功事件。
- Fake client 回 429 時會重試；回 `invalid_grant` 時連線改 `token_invalid`、工作 `blocked`。
- 未連結 Google 時預約 API 仍 2xx，工作 `blocked`。
- payload_hash 相同不呼叫網路層。

**分享**

- provision 呼叫 calendars.insert 與 acl.insert，且 `sendNotifications` 不為 false。
- unshare 呼叫 ACL delete。
- 更換 email 的順序：先 unshare 舊、再 share 新。
- 分享名單 = 心理師（在職且有 Gmail）∪ 行政，去重；擁有者本人被略過且不算多餘；`acl.list` 的 owner 項目不納入比較。
- 同一人兼心理師與行政：只有一筆 rule；從行政名單移除他、他仍是在職心理師 → 不刪 rule；他離職且不在行政名單 → 才刪。
- 離職：分享被移除、日曆與事件仍在、不再更新；日曆裡不屬於他的場次會被清除。
- 每本日曆不含別的心理師的場次；同步重跑不產生重複事件。
- 縮寫純函式：三字名、複姓、兩字名、單字、非中文姓名，且任何結果都不等於完整姓名。

**備註與權限**

- staff/admin 可對任一預約寫備註；心理師寫入 403。
- 負責心理師可讀；其他心理師 GET 回 404；列表不得洩漏他人的 `has_therapist_note`。
- 更新會寫 revision；軟刪後心理師讀不到本文。
- 已讀：負責心理師可標記；他人 403；重複標記冪等。
- 預設不因備註變更而把本文推進 Google。

**Migration**

- 升級、降級再升級，資料仍在；head 鏈結在 `zi9e3f4a5b6e` 之後；沒有 drop 既有業務表。

前端：tsc `--noEmit`、next lint。權限按鈕顯示可用較輕的測試或手動清單（見下）。

手動驗收（連測試 Google 專案，不上正式個案資料）：管理員走完 OAuth（含未驗證警告）、建一個心理師日曆、用另一顆 Gmail 收信並加入、建立／改期／取消各一筆看 Google 是否在數秒內更新；用心理師帳號確認只能看自己的備註與場次。

---

## 12. 分階段 PR（小疊加，各有驗收條件）

每個 PR：pytest、`tsc --noEmit`、`next lint` 全過才 commit；沿用目前慣例先不自行 push。`docs/` 是否進 commit 依既有約定。不要在同一 PR 混進無關重構。

### PR A — 診所設定骨架與 OAuth 連線

從 `feat/room-occupancy`（或當時已合併的 head）切 `feat/gcal-oauth-settings`。

範圍：migration `clinic_settings` + `google_oauth_connections`；加密輔助函式；connect／callback／disconnect／GET 設定；admin 設定頁的連線與標題格式（先存設定、尚未推送）。不打 Calendar API（除 OAuth token 端點以外，正式環境才會碰到）。

驗收：admin 可走完 OAuth（測試專案）並看到已連結 email；staff 看不到連結按鈕；token 密文不進回應；測試全 mock。

### PR B — 日曆佈建與 ACL 分享 UI

分支自 A：`feat/gcal-provision-share`。

範圍：`google_calendars`、心理師 Gmail 欄位、provision／resend／unshare API、行政／管理員對應表。Calendar client 介面 + fake。尚未推事件。

驗收：設定 Gmail 後可建立日曆並分享（fake 斷言 ACL reader + 通知為 true）；更換信箱會先取消舊分享；staff 可操作對應表但不能改全域設定；官方限制（勿短時間建超過 60 個日曆）有節流或明確錯誤。

**實作備註（PR B 已完成，與上面原稿的差異）：**
- migration 是 `zk1a5b6c7d8e_gcal_calendars`（新增 `google_calendars` 與 `users.gcal_share_email`）；備註的 migration 改接在它後面（PR D 要用下一個 revision，不是原稿的 `zk…`）。
- `google_calendars` 多了 `is_missing`（Google 上日曆被手動刪除）；`share_status` 增加 `owner`（心理師信箱就是診所帳號）。
- `PATCH /settings/clinic` **不再接受** `staff_share_emails`（送了回 422）：行政名單只能走 `PUT /settings/google/staff-emails`，才會同步所有日曆。
- 沒有 outbox（PR C 才有）：建立、分享、更換信箱、取消分享都是請求內直接呼叫 Google。名冊停用／恢復心理師時（`PUT /auth/users/{id}/toggle`）會「盡力」同步分享，失敗只標在該日曆上，不影響名冊操作。
- 節流：每小時最多建 50 本日曆（官方建議不要短時間超過 60 本），超過回 429。
- 前端：新頁 `/gcal`「日曆分享」（admin、staff 都能進），放行政分享名單與心理師對應表；`/admin` 的「日曆同步」分頁放連結與標題格式，並連到 `/gcal`。
- 不屬於「個別使用者」的 ACL（公開、網域、群組）一律視為多餘並移除——日曆含個案行程，不許公開。

### PR C — Outbox 工作者與事件推送

分支自 B：`feat/gcal-push`。

範圍：`gcal_outbox`、`appointment_google_events`、預約寫入路徑掛鉤、工作者、resync、健康狀態與 token 無效提示、取消／未到刪事件、改期更新同一 event id、標題函式。iCal 不變。

驗收：§11 中 outbox／隱私／冪等測試全過；手動建立／改期／取消反映到測試日曆；未連結時預約流程不受影響；失敗可重試。

**實作備註（PR C 已完成，與上面原稿的差異）：**
- migration `zl2b6c7d8e9f_gcal_outbox`（`appointment_google_events`、`gcal_outbox`）。PR D 的備註 migration 要接在它後面。
- **入列用 SQLAlchemy flush 事件**（`app/models/gcal_hooks.py`），不是每個路由手動呼叫：新增、批次、改期、換診間、改心理師、取消、未到、報到執行（含結算流程，不必改 `settlement.py`）、刪除都在同一交易入列。只有不經 ORM 的批次 UPDATE（結案取消未來預約，`cases.py`）要明確呼叫 `enqueue_appointments`。
- **每個預約只有一列工作**（`dedupe_key = appt:{id}`，`version` 每次入列加一）。實際動作（upsert／delete）由工作者「執行當下」重讀預約決定；處理期間又有異動則維持待處理，不會誤標 done。
- outbox 與對應表的 `appointment_id` **刻意不設外鍵**：預約（booked）可被硬刪除，刪除後仍要靠對應表去 Google 刪事件。
- 事件 id：`cheer` + 7 位數預約 id（只含 a-v、0-9；曾刪除的同 id 事件 insert 回 409 → 改 update 復活）。
- 沒有 Google 連線（從未連結或已解除）時**不入列**，上線用「全部重新同步」匯入；授權失效（token_invalid）時入列為 blocked。心理師還沒有日曆 → blocked；日曆建好（或重新啟用）後自動把該心理師區間內的預約排入。
- 重試：2、4、8…秒加抖動、上限 15 分鐘，最多 10 次後 failed；429／5xx／網路／用量 403 才重試，其他 4xx 直接 failed。invalid_grant → 連線 token_invalid、全部 blocked。
- 工作者：`python -m app.gcal_worker`（`docker-compose.prod.yml` 新增 `worker` 服務；api 與 worker 也補上 Google／Fernet 環境變數）。領取用 `FOR UPDATE SKIP LOCKED`，處理中標 `running`，超過 10 分鐘視為工作者當掉而收回。
- 新端點：`GET /settings/google/sync`（admin、staff；counts／failed／blocked 清單，只含預約編號、心理師、時間、原因，不含個案資料）、`POST /settings/google/sync/retry`（admin、staff）、`POST /settings/google/sync/resync`（僅 admin；區間依 `resync_lookback_days`／`resync_lookahead_days`，每筆錯開 0.3 秒，並清掉雜湊以覆寫 Google 上被改過的內容、為已取消但仍有事件的預約排刪除）。
- 標題 (a)(b)(c)(d) 與縮寫規則見 `app/services/gcal_titles.py`；個案代號用 `cases.case_code`；事件另帶 `extendedProperties.private.cheerpsyAppointmentId`（只有預約內部 id）。
- **內容規則後續修訂（2026-11-16）**：新增 (d) 個案全名並設為預設（migration `zm3c7d8e9f0a`：放寬 check constraint、改預設；既有設定列若從未被管理員改過 `updated_by_user_id` 為空，就一併改為 (d)，明確選過的值不動）；標題結尾加金額（`appointments.amount` > 0 才顯示；後來決定**描述不放金額**）；描述加備註分段（`note_sections`，目前沒有來源，PR D 接上）。`amount` 已加入入列監看欄位。
- **定位與金額（2026-11-17 更新，優先）**：本系統不負責收款；收款記錄（C）與失約費建議（D）停用，欄位保留。金額必須大於 0（借場地方案 `allows_zero_amount` 例外），標題格式見前面決策第 6 點。折扣、轉帳後五碼、月結、額度池、伴侶付費方不做。以下為 2026-11-16 的原記載（其中收款記錄、失約費、「0＝免費」已被取代）：
- **金額與金流資訊（2026-11-16 更正）**：金額不再是「選填的數字」。自費預約金額**必填**（0＝免費）；機構預約由方案價目帶出應收與個案自付額，建立時存成快照，行政可手動調整（寫稽核）。心理師填、看自己個案預約的真實金額，不歸零。機構方案、價目、交通費、個案額度、收款記錄（未收／已收／免收、方式、時間、經手人）、失約費建議金額屬「金流資訊」，**保留**；核銷、對帳、流水、月結日結、酬勞、零用金、商品、收據編號維持移除。Google 標題金額＝個案這次要付的錢（機構自付額、自費全額）；`self_pay_amount`、`funding_source` 變動會觸發重新同步，收款狀態不會。
- 離職（日曆凍結）：不再更新或刪除他自己的事件；場次改派他人時仍會從他的日曆移除（隱私清理）。
- 前端：`/gcal` 新增「預約同步狀態」卡片（計數、失敗／被擋住清單、重試、admin 才有的全部重新同步、工作者疑似沒在跑的警示）。
- 切換標題格式不會自動全量重推，需按「全部重新同步」。

### PR D — 預約備註給心理師

可與 C 平行（基於 A 或 B 亦可，但合併順序建議 A→B→C，D 只要不改同一檔衝突即可）：`feat/appointment-therapist-notes`。

範圍：備註表與歷程 migration、API、權限、`/appts`／`/calendar` 詳情、心理師今日與班表標記、已讀。不依賴 Google。

驗收：權限矩陣測試全過；其他心理師 404；UI 三處都看得到；預設不推 Google。

### PR E — 打磨與維運

分支自 C（合併 D 後）：`feat/gcal-polish`。

範圍：單人重推、設定文案、維運按鈕、（若時間夠）§7.3 高優先的「預設場次長度」。**不做診間總表。**

驗收：回歸 C 的測試；單人重推只動該心理師的日曆。

合併順序：A → B → C，D 可在 C 之前或之後合進主線，E 最後。

---

## 13. 風險

- **Scope 組合**：`calendar.app.created` + `calendar.acls` 已在沙盒實測可行（見 §0）。殘留風險：此組合列不出日曆清單（`calendarList.list` 403），所以日曆 id 必須自己存好，資料庫遺失或日曆被誤刪時無法自動找回，只能重建。
- **停在 Testing**：會 7 天斷線。緩解：上線檢查清單強制 Production，並在健康狀態顯示 token 年齡／最後成功時間。
- **分享不會自動出現在對方日曆**：心理師漏掉信件會以為功能壞了。緩解：行政流程加上「已通知請對方點加入」、重寄按鈕、設定頁說明。
- **未驗證警告**：管理員可能不敢按繼續。緩解：設定頁先寫「會看到 Google 警告，這是因為應用尚未送審，只有診所帳號會授權」。
- **單一 Gmail 成為單點**：密碼外洩影響所有心理師行程。緩解：兩步驟驗證、權限最小化、事件不含敏感個案資料，降低外洩傷害。
- **Google 側手動改行程被覆蓋／或長期不一致**。緩解：單向策略寫進 UI；不做靜默雙向。
- **姓名縮寫 (c) 仍可能在小診所識別出個案**。緩解：診所已決定預設 (c)；縮寫規則保守（兩字名只顯示姓、無法縮寫退化成 (a)），設定項加一句風險說明，診所可隨時改選 (a)。
- **工作者沒啟動**：預約正常但日曆不更新。緩解：健康狀態顯示「工作者心跳／佇列積壓」，部署清單包含 worker。
- **Migration 自動 upgrade**：與診間約束相同，部署時注意環境變數與工作者，但本階段 migration 不掃資料、失敗模式較單純。

不採用服務帳號作為日曆擁有者：官方不建議，且所有權無法轉移（[calendars.insert](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert)）。沒有 Workspace 也沒有 domain-wide delegation（[服務帳號文件](https://developers.google.com/identity/protocols/oauth2/service-account)）。

---

## 14. 要請診所確認的問題

1. ~~標題格式預設要用 (a)(b)(c) 哪一個？~~ **已決定：預設 (c)。**
2. 個案「代號」實際欄位是什麼？沒有代號時 (b) 是否接受只顯示類型與診間？
3. (c) 的縮寫規則是否接受：三字名取前兩字（陳小美→「陳小」）、複姓取三字、兩字名只顯示姓？外籍或單字名退化成 (a)、不顯示全名是否同意？
4. 行政分享名單要放哪些 Gmail？（診所帳號本人不需要列入；同一人兼心理師與行政不會重複分享。）
5. 取消／未到：本計畫預設**刪除** Google 事件（時段空出）。若希望留下「已取消」灰色事件，需另說。
6. 改期是否可能同時更換心理師？若會，採用「舊日曆刪、新日曆建」。
7. iCal 是否要跟隨標題格式？（建議預設否）
8. 備註要不要做已讀？自動已讀還是手動？（建議：打開詳情且看到備註區塊即已讀）
9. accountant 是否需要只讀備註或設定？建議否。
10. 正式環境的公開網址與 callback URI、隱私權政策要放在哪個網域（Publish 到 Production 需要）？
11. 診所 Gmail 地址為何、由誰保管兩步驟驗證與復原碼？

---

## 15. 官方文件速查

- OAuth 與 token：[https://developers.google.com/identity/protocols/oauth2](https://developers.google.com/identity/protocols/oauth2)
- Testing 7 天過期與 Production：[https://support.google.com/cloud/answer/15549945](https://support.google.com/cloud/answer/15549945)
- 未驗證應用與 100 人上限：[https://support.google.com/cloud/answer/7454865](https://support.google.com/cloud/answer/7454865)、[https://developers.google.com/identity/protocols/oauth2/production-readiness/overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
- 何時不必 verification：[https://support.google.com/cloud/answer/13464323](https://support.google.com/cloud/answer/13464323)
- Sensitive scope 與個人使用例外：[https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- Calendar scopes：[https://developers.google.com/workspace/calendar/api/auth](https://developers.google.com/workspace/calendar/api/auth)
- 建立日曆／勿用服務帳號當擁有者：[https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert)
- 寫入事件與 app.created：[https://developers.google.com/workspace/calendar/api/v3/reference/events/insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- ACL 與通知：[https://developers.google.com/workspace/calendar/api/v3/reference/acl/insert](https://developers.google.com/workspace/calendar/api/v3/reference/acl/insert)
- 分享不會自動加入 CalendarList：[https://developers.google.com/workspace/calendar/api/concepts/sharing](https://developers.google.com/workspace/calendar/api/concepts/sharing)
- 使用者收到分享信並需加入：[https://support.google.com/calendar/answer/37100](https://support.google.com/calendar/answer/37100)
- API 配額與 backoff：[https://developers.google.com/workspace/calendar/api/guides/quota](https://developers.google.com/workspace/calendar/api/guides/quota)
- 產品使用限制（60 個日曆、750 次分享等）：[https://knowledge.workspace.google.com/admin/calendar/avoid-calendar-use-limits](https://knowledge.workspace.google.com/admin/calendar/avoid-calendar-use-limits)
