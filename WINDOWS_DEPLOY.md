# CheerPsy Windows 部署說明書（慈恩伺服器）

把正式站從 Railway 移植到自有的 Windows 機器（固定 IP，`cheerpsy@114.35.230.241`），用 Docker Desktop 跑 api/web/postgres/redis，用 Cloudflare Tunnel 對外連線。

## 架構概覽

```
Internet ── Cloudflare (DNS + Tunnel) ── cloudflared (Windows service)
                                                │
                                    ┌───────────┴───────────┐
                                    │   Docker Desktop        │
                                    │  ┌────────┐ ┌────────┐ │
                                    │  │  web   │ │  api   │ │
                                    │  │ :3000  │ │ :8000  │ │
                                    │  └───┬────┘ └───┬────┘ │
                                    │      └─────┬────┘      │
                                    │       ┌────┴────┐      │
                                    │       │postgres │      │
                                    │       │  redis  │      │
                                    │       └─────────┘      │
                                    └─────────────────────────┘
```

跟 Railway 版最大的差異：這裡用同一份 `docker-compose.prod.yml` 把四個服務全部起在同一台機器上（Railway 是 api/web 各自獨立 service + 兩個 plugin）。

---

## Stage 1：架好環境、用測試資料跑通（不動正式 DNS）

### 1. 安裝必要軟體（SSH 進去執行）

```powershell
winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements
winget install --id Cloudflare.cloudflared -e --silent --accept-source-agreements --accept-package-agreements
```

### 2. 啟用 WSL2（Docker Desktop 需要）

```powershell
wsl --install --no-distro
```

這步通常需要**重開機一次**才會生效，重開機前先跟現場的人確認時間（機器如果同時有其他用途，重開機會中斷）。

### 3. 安裝 Docker Desktop

重開機後：

```powershell
winget install --id Docker.DockerDesktop -e --silent --accept-source-agreements --accept-package-agreements
```

第一次啟動 Docker Desktop 可能需要手動接受一次授權條款（視版本而定，桌面登入後點開 Docker Desktop 圖示確認）。

### 4. 設定開機自動啟動 Docker Desktop

用工作排程器（Task Scheduler）建一個「開機時觸發、不論使用者是否登入、以 cheerpsy 帳號執行」的工作，動作是啟動 `Docker Desktop.exe`。這樣重開機/斷電後不需要有人登入桌面，服務就會自動起來。避免用「自動登入桌面」這種做法（安全性較差，鎖不了螢幕）。

```powershell
$action = New-ScheduledTaskAction -Execute "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "cheerpsy" -LogonType Password -RunLevel Highest
Register-ScheduledTask -TaskName "DockerDesktopAutoStart" -Action $action -Trigger $trigger -Principal $principal
```

`-LogonType Password` 需要互動輸入密碼一次（`Set-ScheduledTask` 或排程器 GUI 都會跳密碼輸入框），無法完全用 SSH 一行指令做完，建議這步用 RDP 或現場操作。

### 5. Clone 專案

```powershell
git clone https://github.com/iamleoluo/cheerpsy.git C:\cheerpsy
cd C:\cheerpsy
git checkout claude/ssh-connection-setup-f7d680   # 或改用 main（合併後）
```

repo 是 public，不需要另外設定 GitHub 認證。

### 6. 建立 `.env.production`

```powershell
Copy-Item .env.production.example .env.production
notepad .env.production
```

用 Git Bash 產生隨機密鑰填進去（`POSTGRES_PASSWORD`、`JWT_SECRET`、`ID_ENCRYPTION_KEY`、`NEXTAUTH_SECRET`）：

```bash
openssl rand -hex 32
```

Stage 1 先用測試網域（例如 `win-test.cheerpsies.com`、`win-test-api.cheerpsies.com`）填 `CORS_ORIGINS` / `NEXT_PUBLIC_API_URL` / `NEXTAUTH_URL`，**不要填正式的 `cheerpsies.com`**，避免跟 Railway 上還在跑的正式站衝突。

### 7. 啟動服務

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml exec api python seed.py
```

`seed.py` 會建立 19 組測試帳號（1 admin + 1 accountant + 17 心理師），密碼見 [README.md](README.md)。

### 8. 建立 Cloudflare Tunnel（Cloudflare Zero Trust dashboard 操作）

這裡沒有 Cloudflare API token，所以這步要手動在 dashboard 做：

1. 登入 Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**
2. Connector 選 `cloudflared`，命名例如 `cheerpsy-windows`
3. 照畫面給的指令在 Windows 機器上安裝成服務（會自動開機啟動，不用另外設排程器）：
   ```powershell
   cloudflared.exe service install <畫面上給的 token>
   ```
4. **Public Hostname** 分別加兩筆（Stage 1 用測試網域）：
   - `win-test.cheerpsies.com` → `http://localhost:3000`
   - `win-test-api.cheerpsies.com` → `http://localhost:8000`
5. Cloudflare 會自動在 DNS 加上對應的 CNAME（proxied，指向 tunnel），不用手動去 DNS 頁籤加

### 9. 驗證

- Windows 機器本機：`curl http://localhost:8000/health`、`curl http://localhost:3000`
- `docker compose -f docker-compose.prod.yml ps` 四個服務都是 `Up`
- 瀏覽器打開 `https://win-test.cheerpsies.com`，用 `admin@cheerpsy.com` / `admin123` 登入成功
- 重開一次 Docker Desktop，確認四個 container 靠 `restart: unless-stopped` 自動回來

---

## Stage 2：正式資料遷移 + DNS 切換（另外確認才做，這裡先列 checklist）

⚠️ 這階段會動到正式流量跟正式個案/財務資料，執行前務必再次確認。

1. **備份 Railway Postgres**：從 Railway 的 Postgres service 取得對外可連的 `DATABASE_PUBLIC_URL`（Variables tab），在能連外網的機器上跑：
   ```bash
   pg_dump --format=custom "$RAILWAY_DATABASE_PUBLIC_URL" > cheerpsy_backup.dump
   ```
2. **傳到 Windows 機器**：`scp cheerpsy_backup.dump cheerpsy@114.35.230.241:C:/cheerpsy/`
3. **還原進 Windows 上的 Postgres container**：
   ```powershell
   docker compose -f docker-compose.prod.yml exec -T postgres pg_restore -U cheerpsy -d cheerpsy --clean --if-exists < cheerpsy_backup.dump
   ```
4. **核對筆數/金額**：比對 Railway 與 Windows 兩邊的 `cases`、`appointments`、`session_records` 筆數，以及月報表總金額，確認一致
5. **把 `.env.production` 的網域改成正式的**：`CORS_ORIGINS`、`NEXT_PUBLIC_API_URL`、`NEXTAUTH_URL` 換成 `cheerpsies.com` 系列，`docker compose build` 重建（`NEXT_PUBLIC_API_URL` 是 build-time 變數）
6. **Cloudflare Tunnel 加正式網域的 Public Hostname**：`cheerpsies.com` → web、`www.cheerpsies.com` → web、`api.cheerpsies.com` → api（會覆蓋掉原本指向 Railway 的 CNAME）
7. **驗證正式網域**：完整跑一次登入、建個案、預約、日結、核銷案流程
8. 確認穩定運作一段時間後，才視情況關閉 Railway 上的 service（先不要刪除，留一段觀察期方便回滾）

### 回滾（如果 Stage 2 出問題）

Cloudflare dashboard → Tunnel 的 Public Hostname 刪掉／改回原本指向 Railway 的 CNAME 記錄即可，Railway 的 service 只要沒關閉就能立刻接手。

---

## 常見問題

### Q: Docker Desktop 重開機後沒有自動啟動
**A:** 檢查工作排程器裡 `DockerDesktopAutoStart` 這個工作的「歷程記錄」，通常是密碼過期或帳號被鎖需要重新輸入密碼（工作排程器的「以密碼登入」機制，帳號密碼變更後要更新）。

### Q: `NEXT_PUBLIC_API_URL` 改了網頁沒反應
**A:** 這是 build-time 變數，改 `.env.production` 後要 `docker compose build web`（不是只 `restart`）。

### Q: cloudflared 服務起不來
**A:** `cloudflared.exe service uninstall` 之後重新用 `service install <token>` 安裝一次；確認 Windows 防火牆沒有擋 outbound 443（一般預設不會擋）。
