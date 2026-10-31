@echo off
REM Windows packaging script for Stock ACB Portfolio Tracker
echo ======================================================================
echo Packaging Stock ACB Portfolio Tracker for Windows (PyInstaller)
echo ======================================================================

REM Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Clean prior build artifacts
if exist "build" rmdir /s /q "build"
if exist "dist\StockACBPortfolioTracker" rmdir /s /q "dist\StockACBPortfolioTracker"

REM Run PyInstaller one-directory packaging
pyinstaller --noconfirm --onedir --windowed ^
    --name "StockACBPortfolioTracker" ^
    --add-data "portfolio_tracker/ui;portfolio_tracker/ui" ^
    --hidden-import "openpyxl" ^
    --hidden-import "pandas" ^
    --hidden-import "plotly" ^
    --hidden-import "PySide6.QtWebEngineWidgets" ^
    --hidden-import "PySide6.QtWebEngineCore" ^
    portfolio_tracker\main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo [SUCCESS] Windows application bundled into: dist\StockACBPortfolioTracker\
    echo Run dist\StockACBPortfolioTracker\StockACBPortfolioTracker.exe to test.
    echo Next: Compile installer.iss with Inno Setup to create setup wizard.
    echo ======================================================================
) else (
    echo.
    echo [ERROR] Packaging failed with exit code %ERRORLEVEL%.
)

pause

