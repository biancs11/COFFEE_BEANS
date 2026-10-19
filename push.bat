@echo off
title Coffee Bean Sorter - Quick Git Push
color 0E

set GIT=C:\Users\User\AppData\Local\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe
cd /d "%~dp0"

echo.
echo  ==========================================
echo    Coffee Bean Sorter - Quick Git Push
echo  ==========================================
echo.

:: Check git exists
if not exist "%GIT%" (
    echo  [ERROR] Git not found. Install from https://git-scm.com/download/win
    pause
    exit /b 1
)

:: Show changed files
echo  Changed files:
"%GIT%" status --short
echo.

:: Check if anything to commit
"%GIT%" status --porcelain > "%TEMP%\git_status.txt"
for %%A in ("%TEMP%\git_status.txt") do if %%~zA==0 (
    echo  Nothing to commit - everything is up to date.
    echo.
    pause
    exit /b 0
)

:: Ask for commit message
set /p MSG="  Enter commit message (or press Enter for auto): "
if "%MSG%"=="" (
    for /f "tokens=1-2 delims= " %%a in ("%date% %time%") do set MSG=update: %%a %%b
)

echo.

:: Stage all
echo  Staging all changes...
"%GIT%" add .
if errorlevel 1 ( echo  [ERROR] git add failed. & pause & exit /b 1 )
echo  Staged OK.

:: Commit
echo  Committing: %MSG%
"%GIT%" commit -m "%MSG%"
if errorlevel 1 ( echo  [ERROR] git commit failed. & pause & exit /b 1 )
echo  Committed OK.

:: Push
echo  Pushing to GitHub...
"%GIT%" push
if errorlevel 1 (
    echo  Retrying with --set-upstream...
    for /f %%b in ('"%GIT%" rev-parse --abbrev-ref HEAD') do "%GIT%" push --set-upstream origin %%b
    if errorlevel 1 ( echo  [ERROR] Push failed. Check your internet or remote URL. & pause & exit /b 1 )
)

echo.
echo  Done! Changes are live on GitHub.
echo.
pause
