# 在 Windows 機器上更新正式站：git pull -> 重建 image -> 重啟 container
# 使用方式：在 C:\cheerpsy 底下執行 .\deploy.ps1

$ErrorActionPreference = "Stop"

Write-Host "==> git pull"
git pull

Write-Host "==> docker compose build"
docker compose -f docker-compose.prod.yml --env-file .env.production build

Write-Host "==> docker compose up -d"
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

Write-Host "==> container 狀態"
docker compose -f docker-compose.prod.yml ps
