@echo off
title Sync to Raspberry Pi - Coffee Bean Sorting System
color 0B

:: ============================================================
::  STEP 1 - EDIT THESE 3 LINES BEFORE RUNNING
:: ============================================================
::
::  PI_USER        = the username on your Raspberry Pi
::  PI_HOST        = IP address of your Raspberry Pi
::                   (run "hostname -I" on the Pi to find it)
::  PI_PROJECT_DIR = where the project lives on the Pi
::
set "PI_USER=coffeebean"
set "PI_HOST=192.168.1.84"
set "PI_PROJECT_DIR=/home/coffeebean/COFFEE_BEANS"
::
:: ============================================================

echo.
echo  ============================================================
echo    Sync to Raspberry Pi - Coffee Bean Sorting System
echo  ============================================================
echo    Target : %PI_USER%@%PI_HOST%
echo    Folder : %PI_PROJECT_DIR%
echo  ============================================================
echo.

:: ---- Check that OpenSSH is installed -----------------------
where ssh >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] ssh.exe not found.
    echo.
    echo  Fix: Settings - Apps - Optional Features - OpenSSH Client
    echo.
    pause
    exit /b 1
)

where scp >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] scp.exe not found.
    echo.
    echo  Fix: Settings - Apps - Optional Features - OpenSSH Client
    echo.
    pause
    exit /b 1
)

:: ---- Test SSH connection ------------------------------------
echo  [1/4] Testing connection to %PI_HOST% ...
echo  (You may be prompted for the Pi password)
echo.
ssh -o ConnectTimeout=6 %PI_USER%@%PI_HOST% "echo connected" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Cannot connect to %PI_USER%@%PI_HOST%
    echo.
    echo  Checklist:
    echo    1. Is the Pi powered on and on the same network?
    echo    2. Ping test:  ping %PI_HOST%
    echo    3. Wrong IP?   Run "hostname -I" on the Pi
    echo    4. Set up SSH key - run in PowerShell:
    echo.
    echo       ssh-keygen -t ed25519 -C "coffeebean-sync"
    echo.
    echo       Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" ^| ssh %PI_USER%@%PI_HOST% "mkdir -p ~/.ssh ^&^& cat >> ~/.ssh/authorized_keys"
    echo.
    pause
    exit /b 1
)
echo    OK - Connected.
echo.

:: ---- Ensure project folder exists on the Pi ----------------
echo  [2/4] Preparing project folder on Pi ...
ssh %PI_USER%@%PI_HOST% "mkdir -p %PI_PROJECT_DIR%/backend/api %PI_PROJECT_DIR%/backend/core %PI_PROJECT_DIR%/frontend/src %PI_PROJECT_DIR%/scripts %PI_PROJECT_DIR%/migrations %PI_PROJECT_DIR%/data/training %PI_PROJECT_DIR%/logs"
echo    OK - Folders ready.
echo.

:: ---- Run the PowerShell sync script ------------------------
echo  [3/4] Syncing files to Pi ...
echo    (First run may take 3-5 minutes - builds frontend on Pi)
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0sync_to_pi.ps1" ^
    -PiUser "%PI_USER%" ^
    -PiHost "%PI_HOST%" ^
    -PiDir  "%PI_PROJECT_DIR%"

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Sync failed. See errors above.
    echo.
    pause
    exit /b 1
)

:: ---- Done --------------------------------------------------
echo.
echo  [4/4] All done!
echo.
echo  ============================================================
echo    Open in browser:
echo      Dashboard : http://%PI_HOST%:8000
echo      Launcher  : http://%PI_HOST%:8000/launcher
echo      Health    : http://%PI_HOST%:8000/health
echo  ============================================================
echo.
echo  Watch live logs from this PC:
echo    ssh %PI_USER%@%PI_HOST% "tail -f %PI_PROJECT_DIR%/logs/server.log"
echo.
pause
