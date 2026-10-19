@echo off
title CoffeeSort — Starting System
color 0A
cd /d "%~dp0.."

echo.
echo  ============================================================
echo   Coffee Bean Sorting System
echo   Color ^& Size Detection
echo  ============================================================
echo.

:: Kill any old instance first
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: Activate venv
if not exist "venv\Scripts\activate.bat" (
    echo  [ERROR] Virtual environment not found at venv\
    echo  Please run: python -m venv venv  then  pip install -r backend\requirements.txt
    pause & exit /b 1
)
call venv\Scripts\activate.bat

echo  [1/3] Starting backend on port 8000...
set PYTHONPATH=%cd%
start "CoffeeSort-Backend" /min cmd /k "cd /d %cd% && call venv\Scripts\activate.bat && set PYTHONPATH=%cd% && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info"

echo  [2/3] Waiting for server to be ready...
timeout /t 5 /nobreak >nul

echo  [3/3] Opening dashboard in browser...
start "" "http://localhost:8000"

echo.
echo  ============================================================
echo   System is RUNNING
echo   Operator : http://localhost:8000
echo   Admin    : http://localhost:8000/admin
echo   Phone    : http://192.168.1.37:8000
echo  ============================================================
echo.
echo  Leave this window open to keep the system running.
echo  Press any key to STOP...
pause >nul

echo  Stopping system...
taskkill /f /fi "WINDOWTITLE eq CoffeeSort-Backend" >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
echo  System stopped.
timeout /t 2 /nobreak >nul
