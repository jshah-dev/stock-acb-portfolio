# Master Engineering Plan: Windows Desktop Portfolio Tracker

## 1. Project Overview & Target Audience
* **Target User:** Non-technical family member (Senior-friendly UX).
* **Platform:** Windows Desktop Application (Offline, standalone, zero-cloud infrastructure, no open public ports).
* **Development Environment:** Cross-platform development and testing on macOS, packaged and deployed as a standalone `.exe` installer for Windows.
* **Core Concept:** Ingest historical Zerodha Tradebook files (Excel/CSV), eliminate duplicates using unique execution identifiers, track immutable chronological transactions in an embedded SQLite database, support manual trade adjustments, manage family accounts safely, provide configurable storage locations (e.g. for Google Drive/OneDrive cloud backup syncing), and calculate the **Adjusted Cost Basis (Effective / House Money Average)**.
* **Key Capabilities:**
  1. **Consolidated Family / Master View:** Calculate combined effective average prices across all family accounts pooled together, alongside isolated per-account views.
  2. **Configurable Database Location (Cloud Backup Friendly):** Allow users to store `portfolio.db` in any custom folder (such as a Google Drive, OneDrive, or external drive folder) with persistent settings (`config.json`) and automated migration tools.
  3. **Risk-Free & House Money Visualization:** When net capital at risk drops to $\le 0$ with active shares held, display `₹0.00 (Risk Free)` with hover tooltips displaying the exact negative effective price and total cash extracted.
  4. **Closed Positions with On-Demand Toggle:** Fully exited positions ($\text{Net Quantity} = 0$) are preserved with their realized P&L; users can toggle their visibility on or off with a single click.
  5. **Sell-Without-Buy Anomaly Detection:** Inter-account or missing buy discrepancies are automatically flagged with a visual warning badge (`⚠️ Negative / Sell without Buy`).
  6. **Dynamic Header Scanner:** Parser dynamically scans the first 25 rows to identify table headers, gracefully skipping arbitrary Zerodha Console metadata or report summary rows.
  7. **Manual Trade & Account Management:** Full UI support to add manual transactions (to fix missing entries or transfers), delete individual mistaken transactions, and add/remove family accounts with safe cascade deletion prompts.
  8. **One-Click Database Backup & Restore:** Senior-friendly export and import of `portfolio.db` for easy offline backups or computer migrations.
  9. **Multi-Tab Excel Report Export:** Generate and download a formatted `.xlsx` workbook containing both the consolidated summary and per-account breakdowns.
  10. **Zero-Hassle Process Lifecycle & Crash-Proof Rendering:** Starts via a standard Windows desktop shortcut, includes hardware acceleration fallbacks (`--disable-gpu`) for older PCs, and terminates cleanly via the window `[X]` button or an on-screen "Close App" button with **zero lingering background processes**.
  11. **Modern Web-Like UI:** Clean styling inspired by modern web dashboards (Tailwind Slate palette, generous whitespace, 14–18px readable typography) paired with 100% offline interactive charts.

---

## 2. Tech Stack & Packaging Choice
* **Language:** Python 3.11+
* **GUI Framework:** `PySide6` (Qt for Python)
* **Embedded Web Engine (Interactive Charts):** `PySide6.QtWebEngineWidgets` (renders Plotly figures locally with offline bundled Plotly JS and GPU fallback flags)
* **Interactive Charting:** `plotly` (self-contained offline mode: `include_plotlyjs=True`)
* **Data Processing & Excel Handling:** `pandas`, `openpyxl`
* **Database:** Embedded `sqlite3` (WAL mode enabled, Foreign Keys enabled)
* **Packaging & Distribution:** `PyInstaller` (One-Directory bundle) + `Inno Setup` (Single-file Windows setup wizard)
* **Local Development Scripts:** `run.sh` for macOS, `build.bat` for Windows packaging

---

## 3. Architecture & File Structure

```text
portfolio_tracker/
├── main.py                     # Application bootstrap & Qt event loop lifecycle (clean shutdown)
├── config.py                   # Settings persistence (config.json), active DB path resolver, migration
├── db.py                       # Safe storage paths, WAL mode, schema DDL, accounts CRUD, backup/restore
├── parser.py                   # Dynamic header row scan, tradebook ingestion, column normalization, deduplication
├── engine.py                   # Adjusted cost basis math, closed positions, anomalous flags
├── exporter.py                 # Multi-tab styled Excel report generator (.xlsx)
├── ui/
│   ├── main_window.py          # Main window shell, unified header bar, exit controls, tab navigation
│   ├── holdings_view.py        # KPI cards, view switcher, date filter, closed toggle, table & tooltips
│   ├── upload_view.py          # Tradebook file importer with visual status badges & manual trade shortcut
│   ├── account_manager_dialog.py # Dialog to add/remove family accounts with transaction count safeguards
│   ├── manual_trade_dialog.py  # Dialog to add missing trades or corporate actions
│   ├── transaction_history_dialog.py # Audit view to inspect and delete individual transactions
│   ├── storage_settings_dialog.py    # Dialog to select custom DB location (Google Drive), migrate DB, backup
│   ├── charts.py               # Interactive Plotly chart builders rendered offline inside QWebEngineView
│   └── styles.py               # Modern CSS-like QSS stylesheet (Tailwind Slate palette)
├── tests/
│   ├── test_config.py          # Configuration loading, saving, and custom DB path resolution
│   ├── test_db.py              # Database initialization, PRAGMAs, backup/restore
│   ├── test_accounts.py        # Account lifecycle and foreign key cascade tests
│   ├── test_manual_trades.py   # Manual transaction insert, audit, and single trade delete
│   ├── test_parser.py          # Dynamic header detection, CSV/XLSX parsing, deduplication
│   ├── test_engine.py          # House money math, risk-free display, closed positions, anomaly flags
│   ├── test_consolidation.py   # Family pooling vs per-account isolation
│   ├── test_cutoff.py          # Historical cutoff date filtering
│   └── test_exporter.py        # OpenPyXL workbook validation
├── run.sh                      # Local macOS development runner
├── build.bat                   # PyInstaller one-directory bundling script for Windows
├── installer.iss               # Inno Setup compiler script for building Windows installer
└── requirements.txt            # Python dependencies
```

---

## 4. Configuration & Database Storage Paths (`config.py` & `db.py`)

### 1. Persistent Settings (`config.json`)
Stored in the user profile directory:
- Windows: `%LOCALAPPDATA%\PortfolioTracker\config.json`
- macOS/Linux: `~/.portfolio_tracker/config.json`

Format:
```json
{
  "db_path": "C:\\Users\\User\\Google Drive\\PortfolioTracker\\portfolio.db",
  "theme": "light"
}
```

### 2. Database Path Resolution Order
1. Environment variable: `PORTFOLIO_DB_PATH` (useful for automated testing).
2. Custom path from `config.json` (e.g. Google Drive / OneDrive path chosen by user).
3. Default fallback:
   * Windows: `%LOCALAPPDATA%\PortfolioTracker\portfolio.db`
   * macOS/Linux: `~/.portfolio_tracker/portfolio.db`

### 3. SQLite PRAGMA Configuration
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;
```

### 4. Schema DDL
```sql
-- 1. Accounts Table: Stores family member portfolios
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,               -- Unique identifier (e.g., 'ZERODHA_DAD', 'ZERODHA_SELF')
    user_name TEXT NOT NULL,                   -- Human-readable label (e.g., "Father's Zerodha")
    broker TEXT NOT NULL DEFAULT 'Zerodha',    -- Broker name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Transactions Table: Stores immutable historical trades & manual adjustments
CREATE TABLE IF NOT EXISTS transactions (
    trade_id TEXT PRIMARY KEY,                 -- Broker trade ID or deterministic SHA-256 or MANUAL_...
    account_id TEXT NOT NULL,                  -- Foreign key to accounts
    symbol TEXT NOT NULL,                      -- Normalized trading symbol (e.g., 'INFY', 'RELIANCE')
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price > 0),
    trade_date TIMESTAMP NOT NULL,             -- ISO-8601 string: YYYY-MM-DD HH:MM:SS
    notes TEXT,                                -- Optional notes (for manual adjustments or audit)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);

-- 3. Query Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_trades_account_symbol_date 
    ON transactions(account_id, symbol, trade_date);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_date 
    ON transactions(symbol, trade_date);

CREATE INDEX IF NOT EXISTS idx_trades_account 
    ON transactions(account_id);
```

---

## 5. Mathematical & Analytical Engine

### Core Formulas:
$$\text{Total Buy Qty} = \sum \text{Buy Qty}, \quad \text{Total Buy Cost} = \sum (\text{Buy Qty} \times \text{Price})$$
$$\text{Total Sell Qty} = \sum \text{Sell Qty}, \quad \text{Total Proceeds} = \sum (\text{Sell Qty} \times \text{Price})$$
$$\text{Net Quantity} = \text{Total Buy Qty} - \text{Total Sell Qty}$$
$$\text{Net Capital at Risk} = \text{Total Buy Cost} - \text{Total Proceeds}$$

### Position Classification:
1. **Active Long Position ($\text{Net Quantity} > 0$ and $\text{Net Capital at Risk} > 0$):**
   $$\text{Effective Avg} = \frac{\text{Net Capital at Risk}}{\text{Net Quantity}}$$
2. **House Money / Risk-Free Position ($\text{Net Quantity} > 0$ and $\text{Net Capital at Risk} \le 0$):**
   * UI displays: `₹0.00 (Risk Free)`
   * Hover tooltip shows: $\text{Raw Effective Avg} = \frac{\text{Net Capital at Risk}}{\text{Net Quantity}}$ (negative cost basis) and total net profit extracted.
3. **Closed Position ($\text{Net Quantity} = 0$):**
   $$\text{Realized Profit/Loss} = \text{Total Proceeds} - \text{Total Buy Cost}$$
   * Hidden by default; visible when the `"Show Closed Positions"` checkbox is enabled.
4. **Anomalous Position ($\text{Net Quantity} < 0$ or Sell without Buy):**
   * Flagged with visual warning: `⚠️ Negative / Sell without Buy`.

---

## 6. Dynamic Ingestion Engine (`parser.py`)
1. **Dynamic Header Scanner:** Scans the first 25 rows of the file to locate the table header matching tokens (`symbol`, `tradingsymbol`, `trade_date`, `type`, `price`, etc.), ignoring metadata rows prepended by Zerodha Console.
2. **Column Normalization & Mapping:** Strips whitespace, converts to lowercase, handles synonyms (`scrip`, `rate`, `qty`, `execution_time`).
3. **Type Normalization:** Dates converted to standard ISO strings (`YYYY-MM-DD HH:MM:SS`), types mapped strictly to `'BUY'` or `'SELL'`.
4. **Idempotency & SHA-256 Fallback:** Uses broker `trade_id` if present; otherwise generates deterministic hash:
   $$\text{SHA256}(\text{account\_id} + \text{symbol} + \text{trade\_date} + \text{quantity} + \text{price} + \text{type})$$
5. **Transactional Ingestion:** Inserts via `INSERT OR IGNORE` inside a single SQLite transaction, rolling back on error and returning `(inserted, skipped, total)`.

---

## 7. Multi-Tab Formatted Excel Exporter (`exporter.py`)
Using `openpyxl`:
1. Prompts user for output path via `QFileDialog.getSaveFileName`.
2. **Tab 1 (`Consolidated Family View`):** Columns: `Stock Symbol`, `Holding Status`, `Total Family Shares`, `Total Capital Deployed`, `Total Realized Out`, `Net Capital at Risk`, `Effective Average (House Money)`, `Realized Profit (Closed)`.
3. **Tab 2 (`Account-Wise Breakdown`):** Columns: `Account Name`, `Stock Symbol`, `Holding Status`, `Shares Held`, `Buy Cost`, `Proceeds Booked`, `Net Capital at Risk`, `Effective Avg Price`, `Anomalies / Flags`.
4. Applies currency formatting (`₹#,##0.00`), bold headers, auto-fitted column widths, and subtle color highlights.

---

## 8. Senior-Friendly Modern UI (`ui/`)
1. **Styling (`styles.py`):** Tailwind Slate palette (`#F8FAFC` background, `#FFFFFF` cards, `#2563EB` primary, `#059669` export, `#DC2626` exit). High contrast, minimum `40px` button height, `38px` table row height, readable `14px-22px` fonts.
2. **Hardware Acceleration Guard:** Configures Qt WebEngine with `--disable-gpu` fallback for crash-proof rendering on older PCs.
3. **Holdings Dashboard (`holdings_view.py`):**
   * Controls bar: Account dropdown, `⚙️ Accounts`, Cutoff date picker, `Show Closed Positions` toggle, `+ Add Manual Trade`, `Audit Trades`, `💾 DB Location`, `Export Excel`, `Close App`.
   * KPI Metric Cards: Net Capital at Risk, Realized Cash Extracted, Active & Risk-Free Stock Counts.
   * Split View: Offline Plotly Donut / Capital Recovery chart on left; responsive holdings table with tooltips on right.
4. **Upload View (`upload_view.py`):** Account selector, file picker, real-time import summary badges, quick links to manual trade and account manager.
5. **Dialogs:**
   * `storage_settings_dialog.py`: View current DB path, select custom directory (e.g. Google Drive), migrate existing database, or trigger backup.
   * `account_manager_dialog.py`: Add and safely delete family accounts.
   * `manual_trade_dialog.py`: Add missing historical trades or off-market adjustments.
   * `transaction_history_dialog.py`: Search, audit, and delete single mistaken trades.
6. **Clean Termination:** `aboutToQuit` signal closes SQLite cleanly, `WA_DeleteOnClose` ensures no orphan background processes.

---

## 9. Packaging & Distribution
1. **macOS Runner (`run.sh`):** Launches local development app directly.
2. **Windows PyInstaller Script (`build.bat`):** Packages into one-directory bundle (`dist/PortfolioTracker/`) including assets and hidden imports (`openpyxl`, `PySide6.QtWebEngineWidgets`).
3. **Inno Setup Script (`installer.iss`):** Compiles single-file setup wizard (`PortfolioTrackerSetup.exe`) with desktop shortcut and uninstaller.
