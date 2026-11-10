@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 start.py
) else (
    python start.py
)
if errorlevel 1 (
    echo.
    echo Install Python 3.12 or newer from https://www.python.org/downloads/
    echo Select "Add Python to PATH" during installation, then try again.
    pause
)
