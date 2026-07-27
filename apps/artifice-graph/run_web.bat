@echo off
REM Launch the ArtificeGraph web UI
cd /d "%~dp0"

echo.
echo === Installing web dependencies ===
python -m pip install -e ".[web]" 2>&1
if errorlevel 1 (
    echo [ERROR] pip install failed. Try manually:
    echo   python -m pip install -e ".[web]"
    pause
    exit /b 1
)

echo === Starting web server ===
echo Visit http://localhost:8766
echo To change port: set CALLOSIP_PORT=XXXX
echo.
echo.
python -m web.server
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Make sure Python 3.11+ is installed.
    pause
)