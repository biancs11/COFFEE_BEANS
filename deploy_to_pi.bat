@echo off
title Deploy to Raspberry Pi - Coffee Bean Sorting System
color 0A

:: ============================================================
::  CONFIGURE — must match sync_to_pi.bat
:: ============================================================
set "PI_USER=coffeebean"
set "PI_HOST=192.168.1.84"
set "PI_PROJECT_DIR=/home/coffeebean/COFFEE_BEANS"
:: ============================================================
::
::  OFFLINE-FIRST DEPLOY
::  Syncs files from this PC directly to the Pi via SSH/SCP.
::  No internet required on the Pi — no git pull, no npm registry.
::
::  What it does:
::    1. Copies all source files to the Pi via sync_to_pi.ps1
::    2. Restarts the server on the Pi (offline mode)
::
::  The Pi only needs local network (same WiFi/cable as this PC).
::
:: ============================================================

echo.
echo  ============================================================
echo    Deploy to Raspberry Pi - Coffee Bean Sorting System
echo    OFFLINE MODE - syncing files directly via SSH
echo    Target : %PI_USER%@%PI_HOST%
echo  ============================================================
echo.

:: ---- Test SSH connection ------------------------------------
echo  [1/3] Checking connection to Pi...
ssh -o ConnectTimeout=6 %PI_USER%@%PI_HOST% "echo ok" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Cannot connect to %PI_HOST%
    echo.
    echo  Checklist:
    echo    1. Is the Pi powered on?
    echo    2. Are both devices on the same WiFi or LAN cable?
    echo    3. Ping test:  ping %PI_HOST%
    echo    4. SSH key set up? Run: ssh-keygen -t ed25519
    echo.
    pause
    exit /b 1
)
echo    OK - Connected.
echo.

:: ---- Sync all source files via SCP -------------------------
echo  [2/3] Syncing source files to Pi...
echo    (copies backend, frontend/src, configs - no internet needed)
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0sync_to_pi.ps1" ^
    -PiUser "%PI_USER%" ^
    -PiHost "%PI_HOST%" ^
    -PiDir  "%PI_PROJECT_DIR%" ^
    -SkipBuild ^
    -SkipRestart

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] File sync failed. See errors above.
    pause
    exit /b 1
)

:: ---- Restart server on Pi (offline - no rebuild) -----------
echo.
echo  [3/3] Restarting server on Pi (offline mode)...
ssh %PI_USER%@%PI_HOST% "bash %PI_PROJECT_DIR%/scripts/pull_and_restart.sh"

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Server restart failed. See errors above.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Deploy complete! (offline sync)
echo    Dashboard : http://%PI_HOST%:8000
echo    Launcher  : http://%PI_HOST%:8000/launcher
echo    Health    : http://%PI_HOST%:8000/health
echo  ============================================================
echo.
echo  Note: To rebuild the frontend on the Pi after syncing:
echo    ssh %PI_USER%@%PI_HOST% "cd %PI_PROJECT_DIR%/frontend && npm run build"
echo.
pause
