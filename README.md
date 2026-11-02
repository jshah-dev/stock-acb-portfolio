# Stock ACB Portfolio Tracker

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%28Qt%206%29-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Offline](https://img.shields.io/badge/Privacy-100%25%20Offline%20%26%20Local-success.svg)]()

**Stock ACB Portfolio Tracker** is an offline, privacy-focused desktop application designed for serious equity investors, swing traders, and family offices to track **Adjusted Cost Basis (ACB)**, **Actual Exposure**, **Booked P&L**, and **Net Exposure** ("House Money") across multiple family accounts.

Unlike standard broker portals that erase historical cost context or display misleading returns following partial profit-taking, this application models equity holdings using an institutional-grade adjusted cost basis ledger with full corporate action symbol mapping and zero-cloud local storage.

---

## Key Features

### 1. 9-Column Transparent ACB Ledger
Track positions with mathematical precision through 9 dedicated columns:

| Column | Header | Description |
|---|---|---|
| **1** | **Stock Symbol** | NSE / BSE ticker symbol (with corporate action canonical aliasing) |
| **2** | **Shares Held** | Current open share quantity |
| **3** | **Total Buy Cost (₹)** | Cumulative acquisition cost across all buy lots |
| **4** | **Total Proceeds (₹)** | Cumulative cash extracted from partial or full sell orders |
| **5** | **Actual Exposure (₹)** | Current capital invested in remaining shares (`Shares Held × Avg Buy Price`) |
| **6** | **Booked P&L (₹)** | Realized profit or loss extracted through sales (`Total Proceeds - Cost of Sold Shares`) |
| **7** | **Net Exposure (₹)** | True capital at risk after accounting for booked profits (`Actual Exposure - Booked P&L`) |
| **8** | **Effective Avg Price (₹)** | Net break-even price per share (`Net Exposure ÷ Shares Held`) |
| **9** | **Status / Flag** | Visual status badge: **Active**, **Risk Free (House Money)**, or **Closed** |

> **Core Mathematical Identity:**  
> ### **Actual Exposure − Booked P&L = Net Exposure**  
> - **Pure House Money (Risk-Free):** When cumulative sell proceeds exceed the total purchase cost (`Net Exposure <= 0`), the remaining shares have zero downside capital risk. Effective Average Price displays as **Risk Free** with a badge.  
> - **Exited / Closed Holdings:** When all shares of a stock have been sold (`Shares Held = 0`), the Effective Average Price cleanly displays **₹0.00** in neutral muted slate, preserving historical booked gains without distortion.
> - **Instant Holdings Search & Autocomplete:** A search input right above the table filters stocks in real time by ticker or status (e.g., `Active`, `Risk Free`, `Closed`), paired with dynamic autocomplete and a live stock counter.
> - **Double-Click Script Audit & Context Menu:** Double-clicking any stock row (or right-clicking) instantly opens the **All Trades** audit dialog pre-filtered to all historical trades for that stock, with direct options to inspect records or record manual adjustments.

---

### 2. Corporate Actions & Symbol Name Changes
Companies periodically undergo rebranding, mergers, demergers, or ticker changes (e.g., `CADILAHC` → `ZYDUSLIFE`, `MOTHERSUMI` → `MOTHERSON`).
- An interactive **Symbol Mapping** dialog allows you to link old ticker names to their canonical new symbol.
- Automatically heals cost basis history across name transitions, preventing false "sell without buy" anomalies and preserving continuous ACB calculations.

### 3. Multi-Account Family Ledger
- Consolidate multiple family members and demat accounts (Self, Spouse, HUF, Parents, Kids).
- Seamlessly switch between the **Consolidated Family View** (pooled holdings) and individual account tabs with a single click.
- **Account Management & Post-Registration Editing:** Safely add, delete, or edit account IDs and Display Names post-registration. Renaming an Account ID automatically and transactionally cascades across all linked historical trades.

### 4. Zerodha Tradebook Ingestion (100% Offline)
- Direct drag-and-drop or multi-file selection for Zerodha tradebook exports (`.xlsx` and `.csv`).
- **Multi-Spreadsheet Batch Ingestion:** Select or drop multiple tradebook files simultaneously (e.g., across multiple financial years like FY21-22, FY22-23, FY23-24) to onboard your complete historical ledger in a single operation.
- **Batch Account Attribution Safety Warning:** Persistent in-app notice and confirmation warnings clarify that by default, all spreadsheets uploaded in a batch are credited to the selected target account, preventing accidental cross-account misattribution.
- **Cross-File Deduplication:** Inter-file SHA-256 transaction fingerprinting ensures duplicate files or overlapping date ranges across spreadsheets in the batch are deduplicated in memory prior to committing, preventing double-counting.
- Smart header detection automatically skips metadata banner rows.
- **Pre-Ingestion Confirmation Safety Layer:** Once parsing is complete, the application prompts the user with a clean, concise confirmation dialog displaying the exact number of trades, files, and date range that will be added to the destination account before writing to the database. If the user cancels, the files remain loaded to allow changing accounts with zero friction.

### 5. Manual Trade Entry & Trade Editing (Splits, Bonuses, Corrections)
- Record off-market transfers, IPO allotments, bonus issues, stock splits, or gift transactions with dedicated preset buttons and real-time ticker autocompletion.
- **Bonus Shares Support (₹0.00 Price):** Bonus shares can be recorded with an execution price of **₹0.00**. Mathematically, this increases share quantity without adding acquisition cost, correctly lowering the average cost basis per share without skewing capital exposure.
- Full "All Trades" audit dialog with instant search, auto-fitting, single trade deletion, and **Trade Editing**:
  - **Unlimited Historical Depth:** Loads the complete trade ledger without arbitrary record limits, ensuring older transactions are never truncated.
  - **Script-Specific Filtering & Live Counter:** Opens directly from any stock in the Holdings table with search pre-filled, accompanied by a dynamic `Showing X of Y trade(s)` status badge.
  - **In-Dialog Account Filter:** Switch between "All Accounts (Consolidated)" and specific family member accounts directly within the audit view.
  - Edit any transaction (quantity, price, date, type, account) to account for stock splits (e.g. 1:2) or bonus issues.
  - Mandatory **Reason for Change** note input to document corporate action adjustments.
  - Dedicated **Confirmation Review Tab** comparing Before vs After values side-by-side with difference highlights before applying changes.
  - Immediately recalculates portfolio cost basis, Actual Exposure, Booked P&L, and Net Exposure upon saving.

### 6. Interactive Visualizations & Charts
- Built with high-performance native Qt Charts (QChart).
- **Capital Allocation (Donut):** Portfolio weightings by stock with real-time percentage banners.
- **Exposure Recovery (Bar):** Visual comparison of Actual Capital Invested vs. Net Capital at Risk side-by-side.
- **Realized P&L Distribution (Bar):** Visual breakdown of cumulative booked profits and losses by stock.
- Instant inspection banner updates on mouse hover with formatted currency tooltips.

### 7. Formatted Excel Reports
- Export professional, multi-tab Excel workbooks (`.xlsx`) generated via `openpyxl`.
- Includes both **Consolidated Family View** and dedicated **Account-Wise Breakdown** sheets with auto-fitted column widths, styled header rows, and formatted currency cells.

### 8. Relocatable SQLite Storage & Cloud Sync
- Single-file SQLite database with **Write-Ahead Logging (WAL)** for ACID transactional integrity and crash resistance.
- Change the database storage folder at any time (e.g., relocate to Google Drive, Dropbox, or OneDrive) to automatically sync your portfolio across multiple machines.

### 9. Modern Native UI & Application Branding
- Custom multi-resolution application icons configured for both macOS (`.icns` / `.png`) and Windows (`.ico`).
- Windows taskbar AppUserModelID integration ensuring crisp desktop taskbar grouping and launcher branding.
- Setup wizard branding with embedded installer icons.

---

## Prerequisites

- **Python:** 3.11, 3.12, 3.13, or 3.14+
- **Operating System:** Windows 10/11, macOS 12+, or modern Linux (Ubuntu 22.04+)
- **Git**
- *(Optional, for Windows Installer packaging)*: [Inno Setup 6](https://jrsoftware.org/isinfo.php)

---

## Development Mode Setup & Execution

### macOS & Linux

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jshah-dev/stock-acb-portfolio.git
   cd stock-acb-portfolio
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Launch the application in development mode:**
   ```bash
   ./run.sh
   ```
   *Alternatively, run directly via Python:*
   ```bash
   python3 -m portfolio_tracker.main
   ```

5. **Run the automated test suite:**
   ```bash
   pytest -v
   ```

---

### Windows

1. **Clone the repository:**
   ```cmd
   git clone https://github.com/jshah-dev/stock-acb-portfolio.git
   cd stock-acb-portfolio
   ```

2. **Create and activate a virtual environment:**
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```cmd
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Launch the application in development mode:**
   Double-click `run.bat` or run:
   ```cmd
   run.bat
   ```
   *Alternatively, run directly via Python:*
   ```cmd
   python -m portfolio_tracker.main
   ```

5. **Run the automated test suite:**
   ```cmd
   pytest -v
   ```

---

## Generating the Windows Executable (.exe) & Installer

End users on Windows **never need to clone code, open a command prompt, or install Python**. You can generate a ready-to-install setup wizard (`StockACBPortfolioTrackerSetup.exe`) using either of the methods below:

### Method 1: GitHub Actions Cloud Build (Recommended — Zero Local Setup)
Build the official Windows setup wizard directly in Microsoft's native Windows cloud environment with zero local toolchain:

1. Push your code to GitHub:
   ```bash
   git push origin main
   ```
2. Navigate to your repository on GitHub → **Actions** tab.
3. Select **Build Windows Application** → click **Run workflow**.
4. GitHub Actions spins up a native `windows-latest` VM, runs the test suite, builds with PyInstaller, and compiles Inno Setup.
5. In ~3 minutes, download the pre-compiled **`StockACBPortfolioTracker-Windows-Setup`** artifact containing **`StockACBPortfolioTrackerSetup.exe`**.
6. *(Optional)* Tagging a release (e.g. `git tag v1.0.0 && git push origin v1.0.0`) automatically publishes a GitHub Release with the `.exe` attached as a direct download link.

---

### Method 2: From WSL (Windows Subsystem for Linux)
If developing on Windows using WSL, you can compile the `.exe` directly from the WSL terminal:

```bash
chmod +x build_windows.sh
./build_windows.sh
```
The script bridges to the host Windows Python and Inno Setup compiler via `cmd.exe`, producing `installer_output/StockACBPortfolioTrackerSetup.exe`.

---

### Method 3: Building Natively on Windows

#### Step 1: Package Binaries with PyInstaller
Run `build.bat` in the project root on a Windows PC:
```cmd
build.bat
```
This produces `dist\StockACBPortfolioTracker\StockACBPortfolioTracker.exe`.

#### Step 2: Build the Setup Wizard with Inno Setup
1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php) (free).
2. Right-click `installer.iss` and choose **Compile** (or run `iscc installer.iss`).
3. Produces `installer_output\StockACBPortfolioTrackerSetup.exe`.

---

## How the Windows User Installs & Runs

Simply send the generated `StockACBPortfolioTrackerSetup.exe` (or GitHub Release link) to the end user:
1. User double-clicks `StockACBPortfolioTrackerSetup.exe`.
2. Standard modern setup wizard installs into `%LocalAppData%\Programs\...` with **zero admin rights / UAC elevation needed**.
3. It launches immediately and adds a **Desktop Shortcut** and **Start Menu entry**.
4. A registered uninstaller is created in Windows *Installed Apps* / *Add or Remove Programs* that cleanly removes binaries while safely keeping user portfolio data intact.

---

## Project Directory Structure

```text
stock-acb-portfolio/
├── .github/
│   └── workflows/
│       └── build-windows.yml       # Cloud CI/CD workflow to compile Windows .exe
├── portfolio_tracker/              # Core application package
│   ├── __init__.py                 # Package version and metadata
│   ├── main.py                     # Application entry point & Qt event loop
│   ├── config.py                   # Runtime configuration & database path resolution
│   ├── db.py                       # SQLite schema, migrations, CRUD, and backup/restore
│   ├── engine.py                   # 9-column ACB ledger calculation engine & KPIs
│   ├── exporter.py                 # Multi-tab styled Excel report generator
│   ├── parser.py                   # Zerodha Excel/CSV parser & deduplication
│   └── ui/                         # PySide6 graphical user interface
│       ├── __init__.py
│       ├── styles.py               # Modern UI theme, color tokens, and widgets
│       ├── main_window.py          # Top header bar, tab navigation, and dialog routing
│       ├── holdings_view.py        # 9-column holdings table, KPI cards, and toolbar
│       ├── upload_view.py          # Tradebook ingestion drop-zone and upload log
│       ├── charts.py               # Interactive Qt Charts (Donut, Recovery, Realized)
│       ├── account_manager_dialog.py # Family account management dialog
│       ├── manual_trade_dialog.py    # Manual trade entry form with autocomplete
│       ├── edit_trade_dialog.py      # Trade edit form with Before/After confirmation tab
│       ├── symbol_mapping_dialog.py  # Corporate action symbol renaming dialog
│       ├── storage_settings_dialog.py# Database location and sync migration dialog
│       └── transaction_history_dialog.py # Trade audit, editing, and deletion dialog
├── tests/                          # 44 automated unit, integration, and UI tests
├── app_icon.ico                    # Windows icon resource (16x16, 32x32, 48x48, 256x256)
├── app_icon.icns                   # macOS icon bundle
├── app_icon.png                    # High-res 512x512 application brand icon
├── build.bat                       # Windows native PyInstaller packaging script
├── build_windows.sh                # Shell script to build Windows .exe on Mac/Linux/WSL
├── installer.iss                   # Inno Setup 6 installer specification
├── run.sh                          # macOS / Linux dev launcher script
├── run.bat                         # Windows dev launcher script
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git exclusion rules
└── README.md                       # Documentation & deployment guide
```

---

## Security & Privacy Assurance

- **100% Offline Operation:** No network calls, telemetry, or analytics. Your financial transactions and net worth never leave your device.
- **Zero Third-Party Broker Credentials:** The application does not require your Zerodha API keys, TOTP secrets, or login passwords. You simply export your tradebook from the Zerodha Console and import it locally.
- **ACID Database Reliability:** Trades are stored locally using SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), preventing database corruption even during unexpected power loss.


