@echo off
title CoffeeSort — Change Camera IP
cd /d "%~dp0.."
echo.
echo  ============================================================
echo   Change IP Webcam Address
echo  ============================================================
echo.
echo  Current setting:
findstr "CAMERA_SOURCE" .env
echo.
set /p NEW_IP="  Enter new phone IP Webcam URL (e.g. http://192.168.1.xx:8080/video): "
if "%NEW_IP%"=="" (
    echo  No input — no changes made.
    pause & exit /b
)

:: Replace the CAMERA_SOURCE line in .env using PowerShell
powershell -Command "(Get-Content '.env') -replace '^CAMERA_SOURCE=.*', 'CAMERA_SOURCE=%NEW_IP%' | Set-Content '.env'"

echo.
echo  Updated! New setting:
findstr "CAMERA_SOURCE" .env
echo.
echo  Restart the system for changes to take effect.
echo  (Run STOP_SYSTEM.bat then START_SYSTEM.bat)
echo.
pause
