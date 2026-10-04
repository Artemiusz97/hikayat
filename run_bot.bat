@echo off
title Hikayat Bot Launcher
cd /d "%~dp0"

echo Starting Hikayat Bot...
echo.

if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found at venv\Scripts\python.exe
    echo Please ensure the venv directory exists.
    echo.
    pause
    exit /b 1
)

venv\Scripts\python.exe bot.py

echo.
echo Bot stopped running.
pause
