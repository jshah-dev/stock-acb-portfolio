"""End-to-End integration test validating full workflow: ingestion, manual trade, calculations, export, backup, and restore."""

from pathlib import Path

import openpyxl
import pytest

from portfolio_tracker.config import set_custom_db_path
from portfolio_tracker.db import (
    add_account,
    backup_database,
    get_accounts,
    init_db,
    insert_manual_transaction,
    restore_database,
)
from portfolio_tracker.engine import get_holdings, get_portfolio_summary
from portfolio_tracker.exporter import export_portfolio_to_excel
from portfolio_tracker.parser import parse_tradebook


def test_full_portfolio_tracker_lifecycle_e2e(tmp_path, monkeypatch):
    """Full lifecycle test simulating the entire user journey."""
    sample_files = list(Path("test_data").glob("*.xlsx")) if Path("test_data").is_dir() else []
    if not sample_files:
        pytest.skip("Real Zerodha tradebook test file not found in test_data/")

    real_file = sample_files[0]

    fake_config = tmp_path / "config.json"
    monkeypatch.setattr("portfolio_tracker.config.get_config_path", lambda: fake_config)

    # 1. Setup custom database location (simulating Google Drive folder)
    custom_gdrive_folder = tmp_path / "GoogleDrive" / "PortfolioTracker"
    db_file = custom_gdrive_folder / "portfolio.db"
    set_custom_db_path(db_file, migrate_existing=False)

    conn = init_db(db_file)

    # Verify default starter accounts
    accounts = get_accounts(conn)
    assert len(accounts) == 2

    # 2. Add Mother's account
    add_account(conn, "ZERODHA_MOM", "Mother's Zerodha")
    assert len(get_accounts(conn)) == 3

    # 3. Ingest real Zerodha file into ZERODHA_SELF
    inserted, dupes, total = parse_tradebook(real_file, "ZERODHA_SELF", conn)
    assert total == 78
    assert inserted == 78
    assert dupes == 0

    # 4. Ingest again to test deduplication
    inserted2, dupes2, total2 = parse_tradebook(real_file, "ZERODHA_SELF", conn)
    assert inserted2 == 0
    assert dupes2 == 78

    # 5. Add manual buy trade for Mother in RELIANCE
    insert_manual_transaction(
        conn=conn,
        account_id="ZERODHA_MOM",
        symbol="RELIANCE",
        transaction_type="BUY",
        quantity=50,
        price=2200.0,
        trade_date="2020-08-01 10:00:00",
        notes="Bonus / Off-market DP transfer",
    )

    # 6. Query Consolidated Family Holdings
    df_family = get_holdings(conn, account_id=None, include_closed=True)
    assert not df_family.empty

    symbols = df_family["symbol"].tolist()
    assert "RELIANCE" in symbols

    # Check executive KPIs
    kpis = get_portfolio_summary(df_family)
    assert kpis["total_realized_proceeds"] > 0
    assert kpis["active_stocks_count"] > 0

    # 7. Export formatted Excel report
    export_path = tmp_path / "E2E_Family_Report.xlsx"
    resolved_export = export_portfolio_to_excel(
        db_conn=conn,
        file_path=export_path,
        include_closed=True,
    )
    assert resolved_export.is_file()

    wb = openpyxl.load_workbook(resolved_export)
    assert "Consolidated Family View" in wb.sheetnames
    assert "Account-Wise Breakdown" in wb.sheetnames

    # 8. Live Snapshot Backup
    backup_path = tmp_path / "Backups" / "portfolio_snapshot.db"
    backup_database(conn, backup_path)
    assert backup_path.is_file()

    conn.close()

    # 9. Restore to a new location
    restored_path = tmp_path / "Restored" / "portfolio_restored.db"
    restore_database(backup_path, restored_path)
    assert restored_path.is_file()

    restored_conn = init_db(restored_path)
    restored_accounts = get_accounts(restored_conn)
    assert len(restored_accounts) == 3
    restored_holdings = get_holdings(restored_conn, include_closed=True)
    assert len(restored_holdings) == len(df_family)
    restored_conn.close()

