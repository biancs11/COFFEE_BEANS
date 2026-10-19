@echo off
title Coffee Bean Sorting System
color 0A
cd /d "c:\wamp64\coffee_bean_sorting"

echo.
echo  ============================================
echo    Coffee Bean Sorting System - Starting
echo  ============================================
echo.

:: ── Build frontend if dist folder is missing ─────────────────────────────
if not exist "frontend\dist\index.html" (
    echo  [!] Frontend not built yet. Building now, please wait...
    cd frontend
    call npm install >nul 2>&1
    call npm run build >nul 2>&1
    cd ..
    echo  Frontend built successfully.
    echo.
)

:: ── Kill anything already on port 8000 ───────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo  [1/3] Launching backend server on port 8000...
start "" /b python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > "logs\server.log" 2>&1

:: ── Wait up to 15 seconds for server ─────────────────────────────────────
echo  [2/3] Waiting for server to be ready...
set /a tries=0
:WAIT
timeout /t 1 /nobreak >nul
set /a tries+=1
powershell -Command "try { Invoke-WebRequest http://localhost:8000/health -UseBasicParsing -TimeoutSec 1 -EA Stop | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto READY
if %tries% geq 15 goto TIMEOUT
goto WAIT

:TIMEOUT
echo.
echo  [!] Server did not start in time.
echo      Check logs\server.log for errors.
echo.
pause
exit /b 1

:READY
echo  [3/3] Server is ready!
echo.
echo  ============================================
echo    System running at: http://localhost:8000
echo  ============================================
echo.

:: ── Open Chrome ──────────────────────────────────────────────────────────
set CHROME=
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe"       set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"         set CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe

if not "%CHROME%"=="" (
    start "" "%CHROME%" --new-window "http://localhost:8000"
) else (
    start "" "http://localhost:8000"
)

echo  Server is running. Close this window to stop.
echo  Logs: c:\wamp64\coffee_bean_sorting\logs\server.log
echo.
pause
