#!/usr/bin/env bash
# ==============================================================================
# build_windows.sh - Cross-Platform Windows Executable Generator
# ==============================================================================
# Generates a standalone Windows .exe / installer from macOS, Linux, or WSL
# without requiring the end user to clone the code or install Python.
#
# Supported Environments:
#   1. WSL (Windows Subsystem for Linux) -> Uses native Windows interop (cmd.exe)
#   2. macOS / Linux with Docker        -> Uses containerized Wine + Python 3.11
#   3. GitHub Actions CI/CD             -> Automated cloud build on windows-latest
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}${BOLD}======================================================================${NC}"
echo -e "${BLUE}${BOLD}   Stock ACB Portfolio Tracker - Windows Executable Builder           ${NC}"
echo -e "${BLUE}${BOLD}======================================================================${NC}"

# Detect execution environment
IS_WSL=false
if grep -qi "microsoft" /proc/version 2>/dev/null || uname -r 2>/dev/null | grep -qi "wsl" || command -v cmd.exe >/dev/null 2>&1; then
    IS_WSL=true
fi

# ------------------------------------------------------------------------------
# CASE 1: Running inside WSL (Windows Subsystem for Linux)
# ------------------------------------------------------------------------------
if [ "$IS_WSL" = true ]; then
    echo -e "${GREEN}[INFO] Detected environment: Windows Subsystem for Linux (WSL)${NC}"
    echo -e "[INFO] Bridging to Windows native toolchain via cmd.exe..."

    # Ensure cmd.exe is reachable
    CMD_EXEC="cmd.exe"
    if ! command -v cmd.exe >/dev/null 2>&1; then
        if [ -f "/mnt/c/Windows/System32/cmd.exe" ]; then
            CMD_EXEC="/mnt/c/Windows/System32/cmd.exe"
        else
            echo -e "${RED}[ERROR] cmd.exe not found in WSL path or /mnt/c/Windows/System32/${NC}"
            exit 1
        fi
    fi

    # Check Windows Python
    WIN_PYTHON=$($CMD_EXEC /c "where python" 2>/dev/null | tr -d '\r' | head -n 1 || true)
    if [ -z "$WIN_PYTHON" ]; then
        echo -e "${YELLOW}[WARNING] Windows Python not found in Windows PATH.${NC}"
        echo -e "Please ensure Python 3.11+ is installed on the Windows host and added to PATH."
        exit 1
    fi
    echo -e "${GREEN}[INFO] Found Windows Python: ${WIN_PYTHON}${NC}"

    # Clean prior builds
    rm -rf build dist/StockACBPortfolioTracker installer_output 2>/dev/null || true

    # Execute build.bat natively on Windows host
    echo -e "${BLUE}[STEP 1/2] Running PyInstaller via build.bat...${NC}"
    $CMD_EXEC /c "build.bat"

    # Search for Inno Setup 6 compiler
    ISCC_PATH=""
    C_DRIVE_ISCC_1="/mnt/c/Program Files (x86)/Inno Setup 6/ISCC.exe"
    C_DRIVE_ISCC_2="/mnt/c/Program Files/Inno Setup 6/ISCC.exe"
    if [ -f "$C_DRIVE_ISCC_1" ]; then
        ISCC_PATH="C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
    elif [ -f "$C_DRIVE_ISCC_2" ]; then
        ISCC_PATH="C:\\Program Files\\Inno Setup 6\\ISCC.exe"
    fi

    if [ -n "$ISCC_PATH" ]; then
        echo -e "${BLUE}[STEP 2/2] Compiling Windows Setup Wizard via Inno Setup...${NC}"
        $CMD_EXEC /c "\"$ISCC_PATH\" installer.iss"
        echo -e "\n${GREEN}${BOLD}======================================================================${NC}"
        echo -e "${GREEN}${BOLD}[SUCCESS] Windows Setup Wizard Generated Successfully!${NC}"
        echo -e "${GREEN}Installer File: installer_output\\StockACBPortfolioTrackerSetup.exe${NC}"
        echo -e "You can distribute this single .exe directly to end users. Zero setup required!"
        echo -e "${GREEN}${BOLD}======================================================================${NC}"
    else
        echo -e "\n${YELLOW}[NOTE] Inno Setup 6 (ISCC.exe) not found on Windows host.${NC}"
        echo -e "${GREEN}[SUCCESS] Standalone application folder generated in:${NC}"
        echo -e "  dist\\StockACBPortfolioTracker\\StockACBPortfolioTracker.exe"
        echo -e "(Optional: Install Inno Setup from jrsoftware.org to bundle into a single setup wizard .exe)"
    fi
    exit 0
fi

# ------------------------------------------------------------------------------
# CASE 2: Running on macOS or Linux (using Docker container with Wine)
# ------------------------------------------------------------------------------
echo -e "${GREEN}[INFO] Detected host OS: $(uname -s) ($(uname -m))${NC}"

# Check Docker availability
DOCKER_AVAILABLE=false
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_AVAILABLE=true
    fi
fi

if [ "$DOCKER_AVAILABLE" = true ]; then
    echo -e "${GREEN}[INFO] Docker daemon is running.${NC}"
    echo -e "[INFO] Building Windows .exe using containerized Wine + Python 3.11 environment (tobix/pywine)..."
    
    # Clean previous build artifacts
    rm -rf build dist installer_output 2>/dev/null || true
    mkdir -p dist

    echo -e "${BLUE}[STEP 1/2] Installing Windows dependencies and packaging with PyInstaller...${NC}"
    docker run --rm \
        -v "$PWD":/src \
        -w /src \
        tobix/pywine:3.11 \
        sh -c "
            wine pip install --upgrade pip && \
            wine pip install -r requirements.txt && \
            wine pyinstaller --noconfirm --onedir --windowed \
                --name 'StockACBPortfolioTracker' \
                --add-data 'portfolio_tracker/ui;portfolio_tracker/ui' \
                --hidden-import 'openpyxl' \
                --hidden-import 'pandas' \
                --hidden-import 'plotly' \
                --hidden-import 'PySide6.QtWebEngineWidgets' \
                --hidden-import 'PySide6.QtWebEngineCore' \
                portfolio_tracker/main.py && \
            wine pyinstaller --noconfirm --onefile --windowed \
                --name 'StockACBPortfolioTrackerPortable' \
                --add-data 'portfolio_tracker/ui;portfolio_tracker/ui' \
                --hidden-import 'openpyxl' \
                --hidden-import 'pandas' \
                --hidden-import 'plotly' \
                --hidden-import 'PySide6.QtWebEngineWidgets' \
                --hidden-import 'PySide6.QtWebEngineCore' \
                portfolio_tracker/main.py
        "

    # Fix file permissions from Docker
    if [ "$(id -u)" != "0" ]; then
        sudo chown -R "$(id -u):$(id -g)" dist/ build/ 2>/dev/null || true
    fi

    echo -e "\n${GREEN}${BOLD}======================================================================${NC}"
    echo -e "${GREEN}${BOLD}[SUCCESS] Windows Executables Generated Successfully via Docker!${NC}"
    echo -e "1. Standalone Portable Executable (Zero install required):"
    echo -e "   -> ${BOLD}dist/StockACBPortfolioTrackerPortable.exe${NC}"
    echo -e "2. Full Application Bundle:"
    echo -e "   -> ${BOLD}dist/StockACBPortfolioTracker/StockACBPortfolioTracker.exe${NC}"
    echo -e "\nDistribute ${BOLD}StockACBPortfolioTrackerPortable.exe${NC} directly to Windows users."
    echo -e "They can double-click it directly without cloning code or installing Python!"
    echo -e "${GREEN}${BOLD}======================================================================${NC}"
    exit 0
fi

# ------------------------------------------------------------------------------
# CASE 3: Docker not running or not installed on macOS / Linux
# ------------------------------------------------------------------------------
echo -e "${YELLOW}${BOLD}[NOTICE] Native Windows cross-compilation requires running Windows Python.${NC}"
echo -e "To generate the Windows .exe directly from macOS or Linux without Windows, you have two options:\n"

echo -e "${BOLD}Option A: Start Docker Desktop (Local Build)${NC}"
echo -e "  1. Start Docker Desktop on your machine."
echo -e "  2. Re-run: ${GREEN}./build_windows.sh${NC}"
echo -e "  -> This will automatically build ${BOLD}dist/StockACBPortfolioTrackerPortable.exe${NC} via Wine.\n"

echo -e "${BOLD}Option B: GitHub Actions Cloud Build (Zero Setup, Recommended)${NC}"
echo -e "  A pre-configured GitHub Actions workflow (.github/workflows/build-windows.yml) is ready."
echo -e "  Whenever you push a tag or trigger it from the GitHub website:"
echo -e "  1. Push code to GitHub:  ${GREEN}git push origin main${NC}"
echo -e "  2. Go to your GitHub repo -> ${BOLD}Actions${NC} tab -> ${BOLD}Build Windows Executable${NC} -> ${BOLD}Run workflow${NC}."
echo -e "  3. Microsoft's native Windows runner builds the setup wizard (.exe) in ~2 minutes."
echo -e "  4. Download the ready-to-run ${BOLD}StockACBPortfolioTrackerSetup.exe${NC} directly from GitHub!"
echo -e "${BLUE}======================================================================${NC}"

