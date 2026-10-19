@echo off
title CoffeeSort — Launcher
color 0B
cd /d "%~dp0"

:MENU
cls
echo.
echo  ============================================================
echo   Coffee Bean Sorting System  ^|  Launcher
echo  ============================================================
echo.
echo   SYSTEM
echo   [1]  Start System          (starts backend + opens browser)
echo   [2]  Stop System
echo.
echo   OPEN IN BROWSER
echo   [3]  Open Operator Dashboard   http://localhost:8000
echo   [4]  Open Admin Dashboard      http://localhost:8000/admin
echo.
echo   SETTINGS
echo   [5]  Change Camera IP          (IP Webcam phone address)
echo   [6]  Change Admin Password
echo   [7]  View Logs
echo.
echo   [8]  Exit
echo.
set /p CHOICE="  Choose an option [1-8]: "

if "%CHOICE%"=="1" call shortcuts\START_SYSTEM.bat & goto MENU
if "%CHOICE%"=="2" call shortcuts\STOP_SYSTEM.bat  & goto MENU
if "%CHOICE%"=="3" start "" "http://localhost:8000"      & goto MENU
if "%CHOICE%"=="4" start "" "http://localhost:8000/admin"& goto MENU
if "%CHOICE%"=="5" call shortcuts\CHANGE_CAMERA_IP.bat      & goto MENU
if "%CHOICE%"=="6" call shortcuts\CHANGE_ADMIN_PASSWORD.bat & goto MENU
if "%CHOICE%"=="7" call shortcuts\VIEW_LOGS.bat             & goto MENU
if "%CHOICE%"=="8" exit

echo  Invalid option. Try again.
timeout /t 1 /nobreak >nul
goto MENU
