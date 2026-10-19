@echo off
title CoffeeSort — View Logs
cd /d "%~dp0.."
echo.
echo  ============================================================
echo   CoffeeSort System Logs
echo  ============================================================
echo.
echo  [1] View live backend log (coffee_sorter.log)
echo  [2] View server log
echo  [3] Open logs folder in Explorer
echo  [4] Exit
echo.
set /p CHOICE="  Choose [1-4]: "

if "%CHOICE%"=="1" (
    powershell -Command "Get-Content 'logs\coffee_sorter.log' -Wait -Tail 50"
)
if "%CHOICE%"=="2" (
    powershell -Command "Get-Content 'logs\server.log' -Wait -Tail 50"
)
if "%CHOICE%"=="3" (
    explorer "logs"
)
