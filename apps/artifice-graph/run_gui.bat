@echo off
REM Launch the Graph Pipeline GUI
cd /d "%~dp0"
python gui.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to launch. Make sure Python 3.11+ is installed and dependencies are set up:
    echo   pip install -e ".[dev]"
    echo.
    pause
)
