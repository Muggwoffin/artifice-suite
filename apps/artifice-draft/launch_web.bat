@echo off
title PersonaeEdit
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.10+ from https://python.org and try again.
    pause
    exit /b 1
)

echo Installing dependencies (first-time setup)...
pip install -q -r requirements.txt 2>nul
pip install -q -r requirements-web.txt 2>nul

echo.
echo Starting PersonaeEdit...
echo The browser will open automatically.
echo Close this window to stop the server.
echo.
python "%~dp0launch_personae_web.pyw" --browser
echo.
pause
