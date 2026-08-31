@echo off
REM Auto-start CheerPsy stack on login. Runs from the Startup folder.

REM 1. Launch Docker Desktop if not already running
tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>NUL | find /I "Docker Desktop.exe" >NUL
if errorlevel 1 (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)

REM 2. Wait for the Docker engine to be ready (poll, up to ~3 minutes)
setlocal enabledelayedexpansion
set /a tries=0
:waitloop
docker version >NUL 2>&1
if not errorlevel 1 goto ready
set /a tries+=1
if !tries! GEQ 36 goto ready
timeout /t 5 /nobreak >NUL
goto waitloop
:ready

REM 3. Bring up the compose stack
cd /d C:\cheerpsy
docker compose -f docker-compose.prod.yml --env-file .env.production up -d >> C:\cheerpsy\autostart.log 2>&1
