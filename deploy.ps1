# 在 Windows 機器上更新正式站：git pull -> 重建 image -> 重啟 container
# 使用方式：在 C:\cheerpsy 底下執行 .\deploy.ps1

$ErrorActionPreference = "Stop"

# --- Docker credential helper 防呆 ---------------------------------------
# 透過 SSH 執行時常拿不到完整的使用者 PATH，Docker Desktop 的 credential
# helper 就會找不到。即使只是拉公開 image（postgres / redis），只要
# ~/.docker/config.json 有 "credsStore": "desktop"，Docker 仍會先呼叫它，
# 失敗訊息是：
#   error getting credentials - err: exec: "docker-credential-desktop":
#   executable file not found in %PATH%
# 第一層：把 Docker Desktop 的預設 bin 目錄補進 PATH。
$dockerBin = "$env:ProgramFiles\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) { $env:PATH = "$dockerBin;$env:PATH" }

# 第二層：補完 PATH 後仍找不到 helper 就先示警。這裡不中止——設定裡若沒有
# credsStore，沒有 helper 也能正常拉公開 image；真的需要時 docker 會自己報錯。
if (-not (Get-Command docker-credential-desktop -ErrorAction SilentlyContinue)) {
    Write-Warning "找不到 docker-credential-desktop（已嘗試 $dockerBin）。"
    Write-Warning "若接下來出現 'error getting credentials'，請見 WINDOWS_DEPLOY.md 常見問題："
    Write-Warning "  Q: docker compose 出現 docker-credential-desktop not found"
}
# -------------------------------------------------------------------------

Write-Host "==> git pull"
git pull

Write-Host "==> docker compose build"
docker compose -f docker-compose.prod.yml --env-file .env.production build

Write-Host "==> docker compose up -d"
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

Write-Host "==> container 狀態"
docker compose -f docker-compose.prod.yml ps
