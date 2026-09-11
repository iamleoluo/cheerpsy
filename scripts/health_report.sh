#!/bin/bash
# CheerPsy review 環境開機健康檢查
# 檢查 systemd 服務、DB 連線、本機/公開 HTTP 端點、CORS、log 異常、磁碟空間、
# build 是否過舊等，並用 zenity 彈窗顯示詳細報告。
#
# 設計原則：不是只看「process 有沒有活著／HTTP code 對不對」（liveness），
# 而是盡量驗證「功能真的有沒有用」（functional）。這份 script 是從一次
# 實際踩到的坑學來的：NextAuth 壞掉時所有 liveness check 全部綠燈，因為
# 壞掉的程式碼路徑（/api/auth/*）從來沒被檢查過。

set -uo pipefail

CONDA_ENV=/home/leoluo/miniconda3/envs/cheerpsy-db
PGDATA=/home/leoluo/cheerpsy-web-server/.pgdata
PROJECT_DIR=/home/leoluo/cheerpsy-web-server
REPORT_DIR="$PROJECT_DIR/health-reports"
mkdir -p "$REPORT_DIR"
TS=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$REPORT_DIR/${TS}.txt"

SERVICES=(cheerpsy-postgres cheerpsy-redis cheerpsy-backend cheerpsy-frontend cheerpsy-tunnel)

PASS=0
FAIL=0
WARN=0
declare -a REPORT_LINES
declare -a FAILED_CHECK_NAMES

log() {
  REPORT_LINES+=("$1")
}

# 執行一個檢查；成功記 PASS，失敗記 FAIL 並附上錯誤細節
check() {
  local name="$1"
  local out
  local rc
  out=$(eval "$2" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    log "✅ PASS - ${name}"
    PASS=$((PASS+1))
  else
    log "❌ FAIL - ${name}"
    if [ -n "$out" ]; then
      log "     └─ $(echo "$out" | tail -3 | tr '\n' ' ')"
    fi
    FAIL=$((FAIL+1))
    FAILED_CHECK_NAMES+=("$name")
  fi
}

# 非致命但值得注意的項目（例如：build 過舊、log 裡有零星 error、磁碟偏高）
warn() {
  local name="$1"
  local detail="$2"
  log "⚠️  WARN - ${name}"
  [ -n "$detail" ] && log "     └─ ${detail}"
  WARN=$((WARN+1))
}

# 有重試機制的 curl 檢查（給需要幾秒暖機時間的服務，如 tunnel）
check_http_retry() {
  local name="$1"
  local url="$2"
  local expect="$3"   # 用 grep -E 比對的 HTTP code pattern，例如 "200|307"
  local max_wait="${4:-20}"
  local waited=0
  local code=""
  while [ $waited -lt $max_wait ]; do
    code=$(curl -s -o /dev/null -m 5 -w "%{http_code}" "$url" 2>/dev/null)
    if echo "$code" | grep -qE "^($expect)$"; then
      log "✅ PASS - ${name} (HTTP ${code}, 等待 ${waited}s)"
      PASS=$((PASS+1))
      return
    fi
    sleep 2
    waited=$((waited+2))
  done
  log "❌ FAIL - ${name} (最後回應: HTTP ${code:-無回應}, 已等待 ${max_wait}s)"
  FAIL=$((FAIL+1))
  FAILED_CHECK_NAMES+=("$name")
}

log "=========================================="
log " CheerPsy 開機健康檢查報告"
log " 時間: $(date '+%Y-%m-%d %H:%M:%S %Z')"
log " 主機: $(hostname)"
log "=========================================="

log ""
log "── systemd 服務狀態 ──"
for svc in "${SERVICES[@]}"; do
  check "$svc (systemd active)" "systemctl --user is-active --quiet $svc"
done

log ""
log "── 服務穩定性（重啟次數）──"
# active 不代表穩定：服務可能一直在 crash-loop，剛好檢查當下是活的。
for svc in "${SERVICES[@]}"; do
  n=$(systemctl --user show "$svc" -p NRestarts --value 2>/dev/null || echo "?")
  if [ "$n" = "?" ]; then
    continue
  elif [ "$n" -ge 3 ] 2>/dev/null; then
    warn "$svc 重啟次數偏高" "本次啟動以來已重啟 ${n} 次，可能不穩定，建議查 log"
  else
    log "✅ PASS - $svc 重啟次數正常 (${n} 次)"
    PASS=$((PASS+1))
  fi
done

log ""
log "── 資料層 ──"
check "PostgreSQL 連線 (5432)" "$CONDA_ENV/bin/psql -h $PGDATA -U cheerpsy -d cheerpsy -c 'SELECT 1;' -t"
check "PostgreSQL migration 版本符合預期 (ae1e6f708c03)" \
  "[ \"\$($CONDA_ENV/bin/psql -h $PGDATA -U cheerpsy -d cheerpsy -t -c 'SELECT version_num FROM alembic_version;' | tr -d ' \n')\" = 'ae1e6f708c03' ]"
check "Redis PING (6379)" "[ \"\$($CONDA_ENV/bin/redis-cli -p 6379 ping)\" = 'PONG' ]"

log ""
log "── 本機服務 ──"
# /health 會實際跑一次 SELECT 1（見 app/routers/health.py），
# 所以這裡驗證的是「backend 自己的 DB 連線設定」是否正常，
# 跟上面直接用 psql 連線的檢查（驗證 Postgres process 本身）是不同層面的東西——
# 兩者都過，才代表 Postgres 沒問題「而且」backend 的 config 也沒接錯。
check "Backend /health 含 DB 連線 (127.0.0.1:8000)" \
  "curl -sf -m 5 http://127.0.0.1:8000/health | grep -q '\"database\":\"ok\"'"
check "Frontend 首頁 (127.0.0.1:3000)" "curl -sf -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000 | grep -qE '^(200|307)$'"

log ""
log "── 對外公開端點 (經 Cloudflare Tunnel) ──"
check_http_retry "https://review.cheerpsies.com" "https://review.cheerpsies.com" "200|307" 30
check_http_retry "https://api-review.cheerpsies.com/docs" "https://api-review.cheerpsies.com/docs" "200" 30

log ""
log "── 功能性檢查（不只看 HTTP code，實際驗證回應內容）──"
# 首頁回 307 只代表「有回應」，不代表登入功能真的能用。
# NextAuth 的 UntrustedHost 之類的錯誤只會在 /api/auth/* 路徑上出現，
# 而且壞掉時通常還是回 200（回傳錯誤頁的 HTML），單看 HTTP code 看不出來，
# 所以這裡直接驗證回應內容是不是預期的 JSON（而不是錯誤頁 HTML）。
AUTH_CHECK_FAILED=0
if curl -sf -m 10 https://review.cheerpsies.com/api/auth/providers 2>/dev/null | grep -q '"credentials"'; then
  log "✅ PASS - NextAuth /api/auth/providers 回傳有效設定"
  PASS=$((PASS+1))
else
  log "❌ FAIL - NextAuth /api/auth/providers 回傳有效設定"
  log "     └─ 服務可能顯示 active，但登入功能實際壞掉（例如 UntrustedHost）"
  FAIL=$((FAIL+1))
  FAILED_CHECK_NAMES+=("NextAuth providers")
  AUTH_CHECK_FAILED=1
fi

# CORS：之前踩過的坑——新增 api-review.cheerpsies.com 這個公開網址時，
# 忘記把它加進 backend 的 CORS_ORIGINS，結果瀏覽器端所有 API 呼叫都被擋掉，
# 但用 curl 直接打 API（沒有 Origin/CORS 限制）完全看不出問題。
cors_header=$(curl -s -i -m 10 -X OPTIONS "https://api-review.cheerpsies.com/notifications" \
  -H "Origin: https://review.cheerpsies.com" \
  -H "Access-Control-Request-Method: GET" 2>/dev/null | tr -d '\r' | grep -i '^access-control-allow-origin:')
if echo "$cors_header" | grep -qi "review.cheerpsies.com"; then
  log "✅ PASS - CORS 允許 review.cheerpsies.com 呼叫 API"
  PASS=$((PASS+1))
else
  log "❌ FAIL - CORS 允許 review.cheerpsies.com 呼叫 API"
  log "     └─ 瀏覽器端呼叫 API 會被擋掉（curl 直接打不會發現，因為沒有 Origin 限制）。檢查 apps/api/.env 的 CORS_ORIGINS"
  FAIL=$((FAIL+1))
  FAILED_CHECK_NAMES+=("CORS")
fi

log ""
log "── SSH 遠端維護通道 (ssh.cheerpsies.com) ──"
# 這裡只檢查「本機看得到的部分」：sshd 有沒有活著、tunnel 設定檔裡的
# SSH ingress 規則還在不在、DNS 還有沒有指過來。至於「Cloudflare Access
# 驗證真的擋得住陌生人」這種端對端測試，需要瀏覽器登入，不適合放進
# 每次開機自動跑的檢查，靠人工偶爾測一次即可（2026-09-08 已手動驗證過）。
check "sshd 服務存活" "systemctl is-active --quiet ssh"
check "sshd 監聽 port 22" "ss -tln | grep -q ':22 '"
check "cloudflared config 含 SSH ingress 規則" \
  "grep -q 'ssh.cheerpsies.com' ~/.cloudflared/config.yml && grep -q 'ssh://localhost:22' ~/.cloudflared/config.yml"
check "ssh.cheerpsies.com DNS 解析正常" "dig +short ssh.cheerpsies.com | grep -qE '^[0-9]+\.'"
log "✅ PASS - SSH 已人工測試打通 (2026-09-08，備註: iamleo789@gmail.com)"
PASS=$((PASS+1))

log ""
log "── 前端 build 新鮮度 ──"
# frontend 是 compile 好的 production build（.next/standalone），不是即時編譯的 dev server。
# 如果之後 git pull 了新程式碼卻忘記重新 build，網站會繼續穩定運作，
# 但實際上跑的是「舊」的程式碼，而且不會有任何錯誤或警告——這種情況目前所有檢查都抓不到，
# 只能比對檔案時間來提示。
BUILD_FILE="$PROJECT_DIR/apps/web/.next/standalone/server.js"
if [ -f "$BUILD_FILE" ]; then
  build_mtime=$(stat -c %Y "$BUILD_FILE")
  newest_src=$(find "$PROJECT_DIR/apps/web/src" "$PROJECT_DIR/apps/web/package.json" -type f -newer "$BUILD_FILE" 2>/dev/null | head -1)
  if [ -n "$newest_src" ]; then
    warn "前端原始碼比目前執行的 build 新" "例如 $newest_src 比 build 新，畫面上看到的可能是舊版程式碼。需要重新 npm run build"
  else
    log "✅ PASS - 前端 build 是最新的（原始碼沒有比 build 新的檔案）"
    PASS=$((PASS+1))
  fi
else
  warn "找不到 standalone build" "$BUILD_FILE 不存在"
fi

# package.json 宣告的依賴是否都真的裝進 node_modules。
# 2026-09-12 踩過：git pull 帶進兩個新依賴（@radix-ui/*）但沒跑 npm install，
# build 直接失敗、frontend 進入 restart loop。上面的 mtime 比對抓不到這種情況
# （checkout 會把 mtime 改成當下，npm install 沒跑也不會留下比 build 新的檔案）。
# 這裡不看時間，直接逐一確認每個依賴的 package.json 存在。
WEB_DIR="$PROJECT_DIR/apps/web"
if [ -f "$WEB_DIR/package.json" ] && command -v node >/dev/null 2>&1; then
  missing_deps=$(cd "$WEB_DIR" && node -e '
    const fs = require("fs");
    const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
    const deps = Object.keys({ ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) });
    const missing = deps.filter(d => !fs.existsSync(`node_modules/${d}/package.json`));
    process.stdout.write(missing.join(" "));
  ' 2>/dev/null)
  if [ -n "$missing_deps" ]; then
    log "❌ FAIL - 前端依賴沒裝齊（package.json 有、node_modules 沒有）"
    log "     └─ 缺：${missing_deps}。需要 cd apps/web && npm install && npm run build"
    FAIL=$((FAIL+1))
    FAILED_CHECK_NAMES+=("前端依賴")
  else
    log "✅ PASS - 前端依賴齊全（package.json 宣告的套件都在 node_modules）"
    PASS=$((PASS+1))
  fi
fi

# standalone build 不會自動帶 .next/static，要手動 cp；漏掉的話頁面會 200 但 JS/CSS 全 404。
STATIC_DIR="$WEB_DIR/.next/standalone/.next/static"
if [ -f "$BUILD_FILE" ]; then
  if [ -d "$STATIC_DIR" ] && [ -n "$(ls -A "$STATIC_DIR" 2>/dev/null)" ]; then
    log "✅ PASS - standalone build 已帶 .next/static"
    PASS=$((PASS+1))
  else
    log "❌ FAIL - standalone build 缺 .next/static（頁面會開但沒有 JS/CSS）"
    log "     └─ 需要 cp -r apps/web/.next/static apps/web/.next/standalone/.next/static"
    FAIL=$((FAIL+1))
    FAILED_CHECK_NAMES+=("standalone static")
  fi
fi

# 服務 process 是否比它跑的程式碼舊（git pull 之後忘了 restart）。
# 2026-09-12 踩到：backend 從開機起一直是舊 process，systemd active、/health ok、
# 所有檢查全綠，但新前端呼叫的 /dashboard/todos、/room-calendar 在舊後端不存在 → 404。
# 比對的是「檔案 mtime vs process 啟動時間」而不是 commit 時間：commit 時間可能早於
# process 啟動（先 commit、後 pull），會漏掉；而 git 只會改寫實際變動的檔案，
# 所以「有檔案比 process 新」就等於「需要 restart」。
service_start_epoch() {
  local ts
  ts=$(systemctl --user show "$1" -p ExecMainStartTimestamp --value 2>/dev/null)
  [ -n "$ts" ] && LC_ALL=C date -d "$ts" +%s 2>/dev/null
}
backend_start=$(service_start_epoch cheerpsy-backend)
if [ -n "$backend_start" ]; then
  stale_py=$(find "$PROJECT_DIR/apps/api/app" -type f -name '*.py' -newermt "@$backend_start" 2>/dev/null | head -1)
  if [ -n "$stale_py" ]; then
    warn "backend process 比程式碼舊（pull 之後沒 restart）" "例如 ${stale_py#$PROJECT_DIR/} 比 process 啟動時間新，API 跑的是舊版路由。需要 systemctl --user restart cheerpsy-backend"
  else
    log "✅ PASS - backend process 是用目前的程式碼啟動的"
    PASS=$((PASS+1))
  fi
fi
frontend_start=$(service_start_epoch cheerpsy-frontend)
if [ -n "$frontend_start" ] && [ -f "$BUILD_FILE" ]; then
  if [ "$(stat -c %Y "$BUILD_FILE")" -gt "$frontend_start" ]; then
    warn "frontend process 比 standalone build 舊（build 之後沒 restart）" "需要 systemctl --user restart cheerpsy-frontend"
  else
    log "✅ PASS - frontend process 是用目前的 build 啟動的"
    PASS=$((PASS+1))
  fi
fi

log ""
log "── 系統時鐘 ──"
# 這台是 Windows/Linux 雙系統。Windows 把 RTC 存成本地時間，Linux 預設當 UTC 讀，
# 所以每次從 Windows 切回來開機都會快 8 小時，等 NTP 校正時服務早已在錯的時間下啟動
# （2026-09-12 踩到：cloudflared 開機 log 一堆 ERR、報告檔的 mtime 在未來、ls -t 排序全錯）。
# 修法是一次性的 `sudo timedatectl set-local-rtc 1`；這裡只負責確認它還在。
if command -v timedatectl >/dev/null 2>&1; then
  local_rtc=$(timedatectl show -p LocalRTC --value 2>/dev/null)
  ntp_synced=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)
  if [ "$local_rtc" = "yes" ]; then
    log "✅ PASS - RTC 以本地時間解讀（雙系統不會開機快 8 小時）"
    PASS=$((PASS+1))
  else
    warn "RTC 被當成 UTC 讀（LocalRTC=${local_rtc:-?}）" "雙系統從 Windows 切回來會快 8 小時，服務在錯的時間下啟動。修法：sudo timedatectl set-local-rtc 1"
  fi
  if [ "$ntp_synced" = "yes" ]; then
    log "✅ PASS - 系統時間已與 NTP 同步"
    PASS=$((PASS+1))
  else
    warn "系統時間尚未與 NTP 同步（NTPSynchronized=${ntp_synced:-?}）" "現在的時間可能是錯的，timestamps／JWT 到期判斷都會受影響"
  fi
fi

log ""
log "── 磁碟空間 ──"
# 用「剩餘空間實際大小 (GB)」判斷，不用百分比——小容量的碟很容易一直卡在
# 80%+ 但其實剩餘空間對這台機器的用量（主要是文字/文件）綽綽有餘。
disk_avail_gb=$(df -BG "$PROJECT_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')
disk_avail_human=$(df -h "$PROJECT_DIR" | tail -1 | awk '{print $4}')
if [ "$disk_avail_gb" -lt 3 ] 2>/dev/null; then
  log "❌ FAIL - 磁碟剩餘空間過低 (剩 ${disk_avail_human})"
  FAIL=$((FAIL+1))
  FAILED_CHECK_NAMES+=("磁碟空間")
elif [ "$disk_avail_gb" -lt 10 ] 2>/dev/null; then
  warn "磁碟剩餘空間偏低 (剩 ${disk_avail_human})" "低於 10G，Postgres 若寫入失敗常常是磁碟滿了，建議留意"
else
  log "✅ PASS - 磁碟空間充足 (剩 ${disk_avail_human})"
  PASS=$((PASS+1))
fi

log ""
log "── 服務 log 異常掃描（即使 service 顯示 active）──"
# 上面每一項都是「針對某個已知問題」的檢查。這一段是反過來：
# 不預設任何具體問題，單純把最近的 log 掃一遍找 ERROR/Exception/Traceback，
# 用來抓「還沒被想到、還沒特別寫檢查」的新問題。可能會有一些正常運作下
# 本來就會出現的訊息（例如某個 library 的 warning），算是雜訊但寧可看到多的。
for svc in "${SERVICES[@]}"; do
  # 只掃「這個 service 目前這次啟動以來」的 log，不然重開機後 journald
  # 如果有保留舊 log，幾個月前的舊錯誤會一直重複出現在每次的報告裡，失去意義。
  started_at=$(systemctl --user show "$svc" -p ActiveEnterTimestamp --value 2>/dev/null)
  if [ -n "$started_at" ] && [ "$started_at" != "n/a" ]; then
    err_lines=$(journalctl --user -u "$svc" --since "$started_at" --no-pager 2>/dev/null \
      | grep -iE "error|exception|traceback|fatal" \
      | grep -viE "error_description|errorpage|ping_group_range|ICMP proxy feature is disabled" \
      | tail -5)
  else
    err_lines=""
  fi
  if [ -n "$err_lines" ]; then
    warn "$svc 本次啟動後的 log 出現疑似錯誤字樣" "$(echo "$err_lines" | tr '\n' ' | ')"
  fi
done

log ""
log "=========================================="
log " 結果: ${PASS} 項通過, ${WARN} 項警告, ${FAIL} 項失敗"
log "=========================================="

# 如果有失敗項目，附上對應 service 的最新 log 方便除錯
if [ $FAIL -gt 0 ]; then
  log ""
  log "── 失敗服務的最新 log（除錯用）──"
  for svc in "${SERVICES[@]}"; do
    if ! systemctl --user is-active --quiet "$svc"; then
      log ""
      log "[$svc 最近 10 行 log]"
      log "$(journalctl --user -u "$svc" -n 10 --no-pager 2>&1)"
    fi
  done
  # NextAuth / CORS 功能性檢查失敗時，即使 frontend/backend service 本身是 active 的，
  # 也要把最近的 auth 相關 log 抓出來，不然看不出來哪裡壞了
  if [ "$AUTH_CHECK_FAILED" -eq 1 ] && systemctl --user is-active --quiet cheerpsy-frontend; then
    log ""
    log "[cheerpsy-frontend 最近的 auth 相關 log（service 本身正常，但功能壞掉）]"
    log "$(journalctl --user -u cheerpsy-frontend -n 200 --no-pager 2>&1 | grep -i 'auth' | tail -10)"
  fi
fi

REPORT_TEXT=$(printf '%s\n' "${REPORT_LINES[@]}")
echo "$REPORT_TEXT" > "$REPORT_FILE"

# 只保留最近 30 份報告
ls -t "$REPORT_DIR"/*.txt 2>/dev/null | tail -n +31 | xargs -r rm -f

# --- 彈出通知 ---
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if [ $FAIL -gt 0 ]; then
  TITLE="❌ CheerPsy 開機檢查：發現 ${FAIL} 項問題 (${PASS} 正常 / ${WARN} 警告)"
  ICON="dialog-error"
  URGENCY="critical"
elif [ $WARN -gt 0 ]; then
  TITLE="⚠️  CheerPsy 開機檢查：${WARN} 項警告值得留意 (${PASS} 項正常)"
  ICON="dialog-warning"
  URGENCY="normal"
else
  TITLE="✅ CheerPsy 開機檢查：全部正常 (${PASS} 項通過)"
  ICON="dialog-information"
  URGENCY="normal"
fi

if command -v notify-send >/dev/null 2>&1; then
  notify-send -u "$URGENCY" -i "$ICON" "$TITLE" "詳細報告已彈出視窗，或見 $REPORT_FILE" || true
fi

if command -v zenity >/dev/null 2>&1; then
  # 前景執行（不 & 背景化）：讓這個 process 就是視窗本身的生命週期，
  # 避免被 systemd/shell 在 script 結束時把背景子行程一起回收掉。
  zenity --text-info --title="$TITLE" --width=780 --height=680 \
    --filename="$REPORT_FILE" --font="Monospace 10" 2>/dev/null
fi

exit 0
