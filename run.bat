@echo off
REM Local runner script for Windows development
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
)

echo [INFO] Launching Stock ACB Portfolio Tracker...
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
"%PYTHON_EXEC%" -m portfolio_tracker.main %*

endlocal

