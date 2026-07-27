@echo off
REM Run the full pipeline demo (no LLM required)
cd /d "%~dp0"
python -m artifice_graph.cli demo
echo.
pause
