@echo off
REM Run the full pipeline demo (no LLM required)
cd /d "%~dp0"
python -m graph_pipeline.cli demo
echo.
pause
