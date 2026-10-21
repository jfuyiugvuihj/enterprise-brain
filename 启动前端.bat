@echo off
setlocal
chcp 65001 >nul
title Enterprise Brain - Backend + Frontend
cd /d "%~dp0"

echo ============================================================
echo   Enterprise Brain - Backend + Latest Frontend
echo   Backend:  http://127.0.0.1:18082
echo   Frontend: http://127.0.0.1:18083/
echo ============================================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found in PATH.
    echo Install Node.js, then run this file again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found in PATH.
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo [ERROR] frontend\package.json not found.
    echo Put this file in the project root and run it from there.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] frontend\node_modules is missing.
    echo Run this once:
    echo     npm --prefix frontend install
    pause
    exit /b 1
)

if not exist "scripts\serve_latest_frontend.mjs" (
    echo [ERROR] scripts\serve_latest_frontend.mjs not found.
    pause
    exit /b 1
)

if not exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo [ERROR] Docker Desktop was not found.
    echo Install Docker Desktop, then run this file again.
    pause
    exit /b 1
)

echo [1/4] Ensuring Docker Desktop is running...
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready

echo Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a DOCKER_WAIT=0

:wait_docker
ping -n 4 127.0.0.1 >nul
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
set /a DOCKER_WAIT+=1
if %DOCKER_WAIT% GEQ 40 (
    echo [ERROR] Docker did not become ready within 120 seconds.
    echo Open Docker Desktop manually, wait for "Engine running", then retry.
    pause
    exit /b 1
)
goto wait_docker

:docker_ready
echo Docker is ready.
echo.

echo [2/4] Starting demo database, Redis, Ollama and latest backend/worker...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$names=@('eb-demo-20261011-3f8e0dd-postgres-1','eb-demo-20261011-3f8e0dd-redis-1','eb-demo-20261011-3f8e0dd-ollama-1','eb-latest-backend-20261019','eb-latest-worker-20261019'); foreach($n in $names){ docker inspect $n *> $null; if($LASTEXITCODE -ne 0){ Write-Host ('[ERROR] container not found: ' + $n); exit 1 }; docker start $n *> $null }"

if errorlevel 1 (
    echo.
    echo [ERROR] One or more required containers are missing.
    echo The demo stack and the latest backend/worker must be created once first.
    echo Ask for the prepared demo startup command if this is a fresh machine.
    pause
    exit /b 1
)

echo [3/4] Waiting for backend health at http://127.0.0.1:18082 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(150); while((Get-Date) -lt $deadline){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18082/api/v1/health' -TimeoutSec 3; if($r.StatusCode -eq 200){ exit 0 } } catch {}; Start-Sleep -Seconds 2 }; exit 1"

if errorlevel 1 (
    echo.
    echo [ERROR] Backend did not become healthy within 150 seconds.
    echo Recent backend logs:
    docker logs --tail 40 eb-latest-backend-20261019
    pause
    exit /b 1
)
echo Backend is healthy.
echo.

netstat -ano | findstr ":18083" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Port 18083 is already listening.
    echo The latest frontend is already running:
    echo     http://127.0.0.1:18083/
    echo Close the other window first if you want to restart it.
    pause
    exit /b 0
)

echo [4/4] Building and starting the latest frontend...
call npm --prefix frontend run build
if errorlevel 1 (
    echo.
    echo [ERROR] Frontend build failed. Read the npm output above.
    pause
    exit /b 1
)

set "EB_API_TARGET=http://127.0.0.1:18082"
set "EB_FRONTEND_PORT=18083"
set "EB_FRONTEND_HOST=0.0.0.0"

echo.
echo ============================================================
echo   Ready
echo   Local:  http://127.0.0.1:18083/
echo   LAN:    http://^<this-computer-LAN-IP^>:18083/
echo   Login:  see PRIVATE-LOGIN.txt for the demo account
echo ============================================================
echo Keep this window open. Press Ctrl+C to stop the frontend.
echo The backend containers keep running in Docker.
echo.

node scripts\serve_latest_frontend.mjs

if errorlevel 1 (
    echo.
    echo [ERROR] The frontend server exited unexpectedly.
    pause
)

endlocal
