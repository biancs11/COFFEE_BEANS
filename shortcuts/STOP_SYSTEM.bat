@echo off
title CoffeeSort — Stopping System
color 0C
echo.
echo  Stopping Coffee Bean Sorting System...
taskkill /f /fi "WINDOWTITLE eq CoffeeSort-Backend" >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
echo  System stopped.
echo.
pause
