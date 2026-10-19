@echo off
:: ============================================================
::  Coffee Bean Sorting System — DEVELOPMENT MODE
::  Runs backend (hot-reload) + Vite frontend dev server.
::  React UI: http://localhost:5173
::  API:      http://localhost:8000
::  API docs: http://localhost:8000/docs
:: ============================================================
title Coffee Bean Sorting System — DEV MODE
color 0B

echo.
echo  ============================================================
echo   Coffee Bean Sorting System  —  DEVELOPMENT MODE
echo  ============================================================
echo.

set "PROJECT=%~dp0.."
cd /d "%PROJECT%"

:: Activate venv
if not exist "venv\Scripts\activate.bat" (
    echo  [SETUP] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r backend\requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: Create logs dir
if not exist "logs" mkdir logs

echo  [1/2] Starting FastAPI backend (port 8000, hot-reload)...
start "CBS - Backend DEV" cmd /k "cd /d %PROJECT% && call venv\Scripts\activate.bat && set PYTHONPATH=%PROJECT% && set APP_ENV=development && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo  [2/2] Starting React dev server (port 5173)...
start "CBS - Frontend DEV" cmd /k "cd /d %PROJECT%\frontend && npm run dev"

timeout /t 4 /nobreak >nul

echo.
echo  Opening browser...
start "" "http://localhost:5173"

echo.
echo  ============================================================
echo   DEV servers running:
echo   Frontend  : http://localhost:5173  (hot reload)
echo   Backend   : http://localhost:8000
echo   API Docs  : http://localhost:8000/docs
echo  ============================================================
echo.
echo  Close the terminal windows to stop.
pause
