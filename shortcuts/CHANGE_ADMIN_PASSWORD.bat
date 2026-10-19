@echo off
title CoffeeSort — Change Admin Password
cd /d "%~dp0.."
echo.
echo  ============================================================
echo   Change Admin Dashboard Password
echo  ============================================================
echo.
echo  Current credentials:
findstr "ADMIN_USERNAME\|ADMIN_PASSWORD" .env
echo.
set /p NEW_USER="  Enter new admin username (leave blank to keep current): "
set /p NEW_PASS="  Enter new admin password (leave blank to keep current): "

if not "%NEW_USER%"=="" (
    powershell -Command "(Get-Content '.env') -replace '^ADMIN_USERNAME=.*', 'ADMIN_USERNAME=%NEW_USER%' | Set-Content '.env'"
    echo  Username updated.
)
if not "%NEW_PASS%"=="" (
    powershell -Command "(Get-Content '.env') -replace '^ADMIN_PASSWORD=.*', 'ADMIN_PASSWORD=%NEW_PASS%' | Set-Content '.env'"
    echo  Password updated.
)
if "%NEW_USER%"=="" if "%NEW_PASS%"=="" (
    echo  No changes made.
)

echo.
echo  New credentials:
findstr "ADMIN_USERNAME\|ADMIN_PASSWORD" .env
echo.
echo  Restart the system for changes to take effect.
pause
