@echo off
:: =============================================================================
::  Coffee Bean Sorting System — AUTO-REFRESH LAUNCHER
::  Starts backend + frontend + git watcher in one click.
::  Monitors local file changes AND GitHub origin/main for new commits.
::  Browser auto-refreshes via Vite HMR (frontend) and server restart (backend).
::
::  Frontend : http://localhost:5173  (Vite dev — hot reload)
::  Backend  : http://localhost:8000  (FastAPI — uvicorn --reload)
::  API Docs : http://localhost:8000/docs
:: =============================================================================
title CoffeeSort — Auto-Refresh Mode
color 0B
cd /d "%~dp0.."

echo.
echo  ============================================================
echo   Coffee Bean Sorting System
echo   AUTO-REFRESH MODE  ^|  GitHub + Local Watch
echo  ============================================================
echo.

set "PROJECT=%~dp0.."
cd /d "%PROJECT%"

:: ── 1. Check git is available ───────────────────────────────────────────────
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] git not found in PATH.
    echo  Install Git for Windows: https://git-scm.com/download/win
    pause & exit /b 1
)

:: ── 2. Quick pull before starting so we're always up-to-date on launch ──────
echo  [0/4] Pulling latest from GitHub origin/main...
git pull origin main --quiet
if %ERRORLEVEL% neq 0 (
    echo  [WARN]  git pull failed ^(no internet? ^). Starting with local code.
)
echo         Done.
echo.

:: ── 3. Ensure venv exists ───────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  [SETUP] Virtual environment not found — creating...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r backend\requirements.txt
    echo.
) else (
    call venv\Scripts\activate.bat
)

:: ── 4. Ensure node_modules exists ───────────────────────────────────────────
if not exist "frontend\node_modules" (
    echo  [SETUP] node_modules not found — installing npm deps...
    cd /d "%PROJECT%\frontend"
    npm install --silent
    cd /d "%PROJECT%"
    echo.
)

:: ── 5. Create logs dir ──────────────────────────────────────────────────────
if not exist "logs" mkdir logs

:: ── 6. Kill any stale instances first ───────────────────────────────────────
echo  [1/4] Clearing stale processes...
taskkill /f /fi "WINDOWTITLE eq CBS-Backend-DEV"  >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq CBS-Frontend-DEV" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq CBS-Watcher"      >nul 2>&1
timeout /t 1 /nobreak >nul

:: ── 7. Start FastAPI backend (--reload watches .py files) ───────────────────
echo  [2/4] Starting backend  (port 8000, auto-reload on .py changes)...
start "CBS-Backend-DEV" /min cmd /k ^
    "cd /d %PROJECT% && call venv\Scripts\activate.bat && set PYTHONPATH=%PROJECT% && set APP_ENV=development && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info"

:: ── 8. Start Vite dev server (HMR watches src/) ─────────────────────────────
echo  [3/4] Starting frontend (port 5173, HMR on src/ changes)...
start "CBS-Frontend-DEV" /min cmd /k ^
    "cd /d %PROJECT%\frontend && npm run dev"

:: ── 9. Wait for both servers to be up ───────────────────────────────────────
echo         Waiting for servers...
timeout /t 6 /nobreak >nul

:: ── 10. Start git watcher (GitHub poll + FileSystemWatcher) ─────────────────
echo  [4/4] Starting Git watcher (polls GitHub every 30s)...
start "CBS-Watcher" /min powershell.exe -ExecutionPolicy Bypass -NoProfile ^
    -File "%PROJECT%\scripts\git-watcher.ps1" ^
    -ProjectDir "%PROJECT%" ^
    -Branch "main" ^
    -PollSeconds 30

timeout /t 2 /nobreak >nul

:: ── 11. Open browser ────────────────────────────────────────────────────────
echo.
echo  Opening dashboard...
start "" "http://localhost:5173"

:: ── 12. Status banner ───────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   System is RUNNING in Auto-Refresh Mode
echo.
echo   Operator  : http://localhost:5173
echo   Admin     : http://localhost:5173/admin
echo   API       : http://localhost:8000
echo   API Docs  : http://localhost:8000/docs
echo   Health    : http://localhost:8000/health
echo.
echo   Auto-refresh triggers:
echo     Local  -- save any .py, .jsx, .js, .css, .env file
echo     GitHub -- new commit pushed to origin/main
echo.
echo   Running processes (minimised):
echo     CBS-Backend-DEV   (uvicorn --reload)
echo     CBS-Frontend-DEV  (vite dev)
echo     CBS-Watcher       (git-watcher.ps1)
echo.
echo   Close this window to STOP everything.
echo  ============================================================
echo.

:: ── 13. Keep window open — closing it kills child processes ─────────────────
:WAIT
timeout /t 10 /nobreak >nul
goto WAIT
