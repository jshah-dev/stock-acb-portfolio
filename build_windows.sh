#!/usr/bin/env bash
# ==============================================================================
# build_windows.sh - Windows Executable Generator (WSL & GitHub Actions)
# ==============================================================================
# Generates a standalone Windows .exe / installer without requiring the end
# user to clone code or install Python.
#
# Supported Environments:
#   1. WSL (Windows Subsystem for Linux) -> Native Windows interop via cmd.exe
#   2. GitHub Actions CI/CD             -> Automated cloud build on windows-latest
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
        echo -e "Distribute this single .exe directly to end users. Zero setup required!"
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
# CASE 2: Running on macOS or native Linux
# ------------------------------------------------------------------------------
echo -e "${GREEN}[INFO] Detected host OS: $(uname -s) ($(uname -m))${NC}"
echo -e "${YELLOW}${BOLD}[NOTICE] PySide6 (Qt6) relies on native Windows C++ DLLs and cannot be cross-compiled locally on macOS/Linux.${NC}"
echo -e "Instead, use the included GitHub Actions workflow to build the standalone .exe on Microsoft's native Windows runners.\n"

echo -e "${BOLD}How to generate the Windows .exe via GitHub Actions (Zero Setup):${NC}"
echo -e "  1. Push your code to GitHub:  ${GREEN}git push origin main${NC}"
echo -e "  2. Go to your GitHub repository -> ${BOLD}Actions${NC} tab."
echo -e "  3. Select ${BOLD}Build Windows Application${NC} and click ${BOLD}Run workflow${NC}."
echo -e "  4. In ~3 minutes, download the pre-compiled ${BOLD}StockACBPortfolioTracker-Windows-Setup${NC} artifact."
echo -e "     -> Inside is ${BOLD}StockACBPortfolioTrackerSetup.exe${NC} ready to distribute!"
echo -e "\n${BOLD}For official releases:${NC}"
echo -e "  Tag a commit: ${GREEN}git tag v1.0.0 && git push origin v1.0.0${NC}"
echo -e "  -> GitHub will automatically build and publish the installer to your repository Releases page."
echo -e "${BLUE}======================================================================${NC}"
