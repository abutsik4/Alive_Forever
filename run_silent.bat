@echo off
cd /d "%~dp0"

REM Check if pythonw is available (runs without console)
where pythonw >nul 2>&1
if errorlevel 1 (
    REM Fallback to python if pythonw not found
    python keep_alive.py
) else (
    REM Run without console window
    start "" pythonw keep_alive.py
)
