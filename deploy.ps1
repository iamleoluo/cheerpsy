# 在 Windows 機器上更新正式站：git pull -> 重建 image -> migration -> 重啟 container
# 使用方式：在 C:\cheerpsy 底下執行 .\deploy.ps1
#
# 本檔存為 UTF-8 with BOM。Windows PowerShell 5.1 對沒有 BOM 的 .ps1 會用
# ANSI（本機為 big5）解讀，字串裡的中文會被拆碎並提早終止字串。不要移除 BOM。

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

# --- Docker credential 防呆 ------------------------------------------------
# 透過 SSH 執行時，Docker Desktop 設定的 credential helper（wincred）會失敗：
#   error getting credentials - err: exit status 1,
#   out: A specified logon session does not exist. It may already have been terminated.
# 因為 wincred 要存取 Windows 認證管理員，而非互動式的 SSH session 沒有可用的
# logon session。即使只是拉公開 image（postgres / redis / python / node）也會整個失敗。
#
# 解法：Docker CLI 只有在 PATH 上找得到 docker-credential-* 才會用它，找不到就
# fallback 成純文字 store。所以 build 期間把 Docker 的 resources bin 目錄從 PATH
# 拿掉，並用絕對路徑呼叫 docker.exe，再指向一份不含 credsStore 的 DOCKER_CONFIG。
# 本專案不需登入任何 registry（公開 image + 本機 build），拿掉完全不影響。
# 詳見 WINDOWS_DEPLOY.md 常見問題。
$DockerBin = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
$Docker = Join-Path $DockerBin 'docker.exe'
if (-not (Test-Path $Docker)) {
    throw "找不到 docker.exe：$Docker"
}

$CiConfig = Join-Path $RepoRoot '.docker-ci'
if (-not (Test-Path $CiConfig)) { New-Item -ItemType Directory -Path $CiConfig | Out-Null }
# 必須是「無 BOM」的 UTF-8，Docker 的 JSON parser 讀到 BOM 會直接判定格式錯誤
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $CiConfig 'config.json'), '{"auths":{}}', $Utf8NoBom)

$SavedPath = $env:PATH
$BuildPath = ($SavedPath -split ';' | Where-Object { $_ -notlike '*Docker\Docker\resources\bin*' }) -join ';'
$env:DOCKER_CONFIG = $CiConfig
# ---------------------------------------------------------------------------

$Compose = @('compose', '-f', 'docker-compose.prod.yml', '--env-file', '.env.production')

try {
    Write-Host '==> git pull'
    # git 需要原本的 PATH
    $env:PATH = $SavedPath
    git pull
    if ($LASTEXITCODE -ne 0) { throw "git pull 失敗（exit $LASTEXITCODE）" }

    # 以下 docker 步驟改用受限 PATH
    $env:PATH = $BuildPath

    Write-Host '==> docker compose build'
    & $Docker @Compose build
    if ($LASTEXITCODE -ne 0) { throw "build 失敗（exit $LASTEXITCODE）" }

    Write-Host '==> docker compose up -d'
    & $Docker @Compose up -d
    if ($LASTEXITCODE -ne 0) { throw "up 失敗（exit $LASTEXITCODE）" }

    Write-Host '==> alembic upgrade head'
    & $Docker @Compose exec -T api alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "migration 失敗（exit $LASTEXITCODE）" }

    Write-Host '==> container 狀態'
    & $Docker @Compose ps

    Write-Host '==> 健康檢查'
    $health = (Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing).Content
    Write-Host "    api  : $health"
    $webCode = (Invoke-WebRequest -Uri 'http://localhost:3000/login' -UseBasicParsing).StatusCode
    Write-Host "    web  : HTTP $webCode"
    Write-Host '==> 部署完成'
}
finally {
    $env:PATH = $SavedPath
    Remove-Item Env:DOCKER_CONFIG -ErrorAction SilentlyContinue
}
