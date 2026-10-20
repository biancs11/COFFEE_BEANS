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

:: ---- Clone repo if project folder does not exist -----------
echo  Checking if project exists on Pi...
ssh %PI_USER%@%PI_HOST% "test -d %PI_PROJECT_DIR% && echo exists || echo missing" > "%TEMP%\pi_check.txt" 2>&1
set /p PI_DIR_STATUS=<"%TEMP%\pi_check.txt"

if "%PI_DIR_STATUS%"=="missing" (
    echo  Project folder not found on Pi - cloning from GitHub...
    ssh %PI_USER%@%PI_HOST% "git clone https://github.com/biancs11/COFFEE_BEANS.git %PI_PROJECT_DIR%"
    if %errorlevel% neq 0 (
        echo  [ERROR] Git clone failed. Check Pi internet connection.
        pause
        exit /b 1
    )
    echo  OK - Project cloned.
    echo.
    echo  Running first-time setup on Pi - this takes 5-10 minutes...
    ssh %PI_USER%@%PI_HOST% "bash %PI_PROJECT_DIR%/scripts/setup_rpi.sh"
    echo.
    echo  Setup complete. Rerun this script to deploy.
    pause
    exit /b 0
)
echo  Project folder found.
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
