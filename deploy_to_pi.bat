@echo off
title Deploy to Raspberry Pi - Coffee Bean Sorting System
color 0A

:: ============================================================
::  Same Pi settings as sync_to_pi.bat
:: ============================================================
set "PI_USER=coffeebean"
set "PI_HOST=192.168.1.84"
set "PI_PROJECT_DIR=/home/coffeebean/COFFEE_BEANS"
:: ============================================================

echo.
echo  ============================================================
echo    Deploy to Raspberry Pi - Coffee Bean Sorting System
echo  ============================================================
echo    This will: git pull on the Pi + rebuild + restart server
echo    Target   : %PI_USER%@%PI_HOST%
echo  ============================================================
echo.

:: ---- Test connection ----------------------------------------
echo  Checking connection to Pi...
ssh -o ConnectTimeout=5 %PI_USER%@%PI_HOST% "echo ok" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Cannot connect to %PI_HOST%
    echo  Make sure the Pi is on and on the same network.
    pause
    exit /b 1
)
echo  Connected OK.
echo.

:: ---- Run pull_and_restart.sh on the Pi ---------------------
echo  Running pull_and_restart.sh on the Pi...
echo  (This will take 2-4 minutes for the frontend build)
echo.
ssh %PI_USER%@%PI_HOST% "bash %PI_PROJECT_DIR%/scripts/pull_and_restart.sh"

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Deploy failed. See output above.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Deploy complete!
echo    Dashboard : http://%PI_HOST%:8000
echo    Launcher  : http://%PI_HOST%:8000/launcher
echo  ============================================================
echo.
pause
