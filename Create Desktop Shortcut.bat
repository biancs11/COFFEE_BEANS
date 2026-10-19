@echo off
title Creating Desktop Shortcut...

:: ── Find Chrome ──────────────────────────────────────────────────────────────
set CHROME=
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
)

if "%CHROME%"=="" (
    echo [ERROR] Google Chrome not found on this machine.
    pause
    exit /b 1
)

:: ── Create the .url shortcut on Desktop ──────────────────────────────────────
set SHORTCUT=%USERPROFILE%\Desktop\Coffee Bean Sorter.url

(
echo [InternetShortcut]
echo URL=http://localhost:8000
echo IconFile=%CHROME%
echo IconIndex=0
echo HotKey=0
echo IDList=
) > "%SHORTCUT%"

echo.
echo  Shortcut created on your Desktop!
echo  File: %SHORTCUT%
echo.
echo  Double-click "Coffee Bean Sorter" on your desktop to open the system.
echo.
pause
