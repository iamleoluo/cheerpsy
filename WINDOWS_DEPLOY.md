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

### 開機自動啟動：`start-cheerpsy.bat`

repo 根目錄的 `start-cheerpsy.bat` 是給**開機／登入時自動把整個 stack 叫起來**用的，放進使用者的「啟動」資料夾（`shell:startup`）即可。它做三件事：

1. 檢查 `Docker Desktop.exe` 有沒有在跑，沒有就啟動它
2. 輪詢 `docker version` 等引擎就緒，每 5 秒一次、最多 36 次（約 3 分鐘）後放行
3. `cd C:\cheerpsy` 後執行 `docker compose ... up -d`，輸出附加到 `C:\cheerpsy\autostart.log`

它跟前面第 4 節的工作排程器是**兩種擇一的做法**：排程器版只負責啟動 Docker Desktop、且不需要有人登入；這支 .bat 連 compose stack 也一起帶起來，但要等到使用者登入才會觸發。目前主機上採用的是這支 .bat。

日常更新程式碼請用 `deploy.ps1`（會先 `git pull` 再重建 image），不要用這支——它只做 `up -d`，不會拉新版程式碼。

> ⚠️ `autostart.log` 已被 `.gitignore` 的 `*.log` 規則涵蓋，不會進版控。

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

### Q: `docker compose` 出現 `error getting credentials`

**2026-08-31 在本機（114.35.230.241）實測確認並已解決，`deploy.ps1` 現在會自動處理。**

透過 SSH 執行 build 時會看到：

```
error getting credentials - err: exit status 1,
out: `A specified logon session does not exist. It may already have been terminated.`
```

**原因：** `%USERPROFILE%\.docker\config.json` 的 `credsStore` 指向 `wincred`，而
`docker-credential-wincred.exe` 需要存取 Windows 認證管理員 —— 非互動式的 SSH session
沒有可用的 logon session，因此必定失敗。即使拉的是公開 image（`postgres`、`redis`、
`python`、`node`）也一樣整個 build 中斷。桌面手動跑沒事、SSH 進去跑就炸，就是這個原因。

#### 實測過程中被推翻的三種做法（別再走一次）

| 做法 | 結果 |
|---|---|
| 找出 `docker-credential-desktop.exe` 加進 PATH | ❌ 整台機器上**不存在**這支。只有 `wincred` 與 `ecr-login` |
| 從 config.json **移除** `credsStore` | ❌ **反而更糟**。移除後 Docker 改用 Windows 預設 store，還是 `wincred` |
| 設成 `"credsStore": ""` | ❌ 空字串一樣被當成「用預設」，照樣走 wincred |

> 另外兩個實測踩到的坑：
> 1. Docker Desktop 會**自己改寫** config.json。第一次讀到的值是 `desktop`（一支不存在的
>    helper，所以當時反而「碰巧能用」＝靜默 fallback 免認證），之後被它自動改成 `wincred`。
>    不要假設這個檔案的內容不會變。
> 2. 用 `Set-Content -Encoding utf8` 改寫 config.json 會寫入 **BOM**，Docker 的 Go JSON
>    parser 直接吃不下：`invalid character 'ï' looking for beginning of value`。
>    要用 `[System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))`。

#### ✅ 實際可行的解法

Docker CLI 只有在 **PATH 上找得到** `docker-credential-*` 時才會呼叫它，找不到就 fallback
成純文字 store。所以在 build 期間：

1. 把 `C:\Program Files\Docker\Dockeresourcesin` **從 PATH 移除**
2. 用**絕對路徑**呼叫 `docker.exe`（它就住在那個被移除的目錄裡）
3. `DOCKER_CONFIG` 指向一份不含 `credsStore` 的乾淨設定

`deploy.ps1` 已內建這三步，正常情況下直接跑即可。本專案不需要登入任何 registry
（公開 image ＋ api/web 為本機 build），拿掉認證完全不影響。

手動要重現時：

```powershell
$docker = "$env:ProgramFiles\Docker\Dockeresourcesin\docker.exe"
$env:DOCKER_CONFIG = "C:\cheerpsy\.docker-ci"   # 內含 {"auths":{}}，無 BOM
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notlike "*Docker\Dockeresourcesin*" }) -join ';'
& $docker compose -f docker-compose.prod.yml --env-file .env.production build
```

> ⚠️ PATH 只留 `system32` 會讓 `git` 也消失，`git pull` 那步要用原本的 PATH。
> `deploy.ps1` 是分段切換的，不是整支都用受限 PATH。

> 之後若真的需要推拉私有 registry 的 image，最乾淨的做法是從**互動式桌面 session**
> （RDP 或現場）執行一次 `docker login`，或改用不依賴 Windows 認證管理員的 helper。

### Q: 主機 build 卡在 `npm ci` 說 lock file 不同步

完整訊息會列出 `Missing: @emnapi/core@... from lock file` 之類的項目。

**原因：** `package-lock.json` 是在 Windows 上產生的，`@emnapi/*` 這類套件屬於平台相依的
optional dependency，Windows 解析出來的依賴樹缺少 linux/alpine 變體，`npm ci` 在
`node:18-alpine` image 內就會判定與 `package.json` 不同步。

**解法：** 在與 image 相同的環境內重新產生 lockfile，然後 commit：

```bash
docker run --rm -v "C:/path/to/repo/apps/web:/app" -w /app node:18-alpine   npm install --package-lock-only
```

