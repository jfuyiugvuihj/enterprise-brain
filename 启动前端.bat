@echo off
setlocal
chcp 65001 >nul
title Enterprise Brain - Latest Frontend
cd /d "%~dp0"

echo ============================================================
echo   Enterprise Brain - Latest Frontend
echo   Latest dist + real backend (127.0.0.1:18082)
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

netstat -ano | findstr ":18083" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Port 18083 is already listening.
    echo The latest frontend is probably already running.
    echo Open: http://127.0.0.1:18083/
    echo To restart it, close the other window first.
    pause
    exit /b 0
)

echo [1/3] Building frontend from the current source...
call npm --prefix frontend run build
if errorlevel 1 (
    echo.
    echo [ERROR] Frontend build failed. Read the npm output above.
    pause
    exit /b 1
)

echo.
echo [2/3] Checking backend http://127.0.0.1:18082 ...
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18082/api/v1/health' -TimeoutSec 3).StatusCode } catch { '0' }"`) do set "EB_HEALTH=%%H"
if not "%EB_HEALTH%"=="200" (
    echo [WARN] Backend health check did not return 200.
    echo The page will open, but data/login calls may fail.
    echo Start the latest backend on 127.0.0.1:18082 first.
    echo.
)

echo.
echo [3/3] Starting the latest frontend...
echo   Local:  http://127.0.0.1:18083/
echo   LAN:    http://^<this-computer-LAN-IP^>:18083/
echo   API:    http://127.0.0.1:18082/
echo.
echo Keep this window open. Press Ctrl+C to stop.
echo.

set "EB_API_TARGET=http://127.0.0.1:18082"
set "EB_FRONTEND_PORT=18083"
set "EB_FRONTEND_HOST=0.0.0.0"
node scripts\serve_latest_frontend.mjs

if errorlevel 1 (
    echo.
    echo [ERROR] The frontend server exited unexpectedly.
    pause
)

endlocal
