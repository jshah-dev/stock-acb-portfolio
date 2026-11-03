"""Unit tests for the multi-tab formatted Excel export generator."""

from pathlib import Path

import openpyxl
import pytest

from portfolio_tracker.db import init_db, insert_manual_transaction, insert_pnl_adjustment
from portfolio_tracker.exporter import export_portfolio_to_excel


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "exporter_test.db"
    conn = init_db(test_db)

    # Seed test transactions across two accounts
    # Account 1: ZERODHA_DAD
    insert_manual_transaction(conn, "ZERODHA_DAD", "INFY", "BUY", 100, 1500.0, "2026-01-10 10:00:00")
    insert_manual_transaction(conn, "ZERODHA_DAD", "INFY", "SELL", 40, 1800.0, "2026-01-15 11:00:00")
    insert_manual_transaction(conn, "ZERODHA_DAD", "RELIANCE", "BUY", 50, 2400.0, "2026-01-20 12:00:00")

    # Account 2: ZERODHA_SELF
    # Pure house money stock
    insert_manual_transaction(conn, "ZERODHA_SELF", "FREE_STK", "BUY", 100, 100.0, "2026-02-01 10:00:00")
    insert_manual_transaction(conn, "ZERODHA_SELF", "FREE_STK", "SELL", 80, 200.0, "2026-02-10 11:00:00")

    # Closed position stock
    insert_manual_transaction(conn, "ZERODHA_SELF", "DONE_STK", "BUY", 20, 50.0, "2026-02-05 10:00:00")
    insert_manual_transaction(conn, "ZERODHA_SELF", "DONE_STK", "SELL", 20, 75.0, "2026-02-12 11:00:00")

    # Seed P&L adjustment
    insert_pnl_adjustment(
        conn,
        account_id="ZERODHA_SELF",
        amount=120.50,
        adjustment_date="2026-02-15",
        category="BROKERAGE_CHARGES",
        direction="LOSS",
        symbol="DONE_STK",
        notes="Q4 DP & AMC",
    )

    yield conn
    conn.close()


def test_export_portfolio_to_excel(db_conn, tmp_path):
    """Verify that export_portfolio_to_excel creates valid multi-tab formatted workbook."""
    output_xlsx = tmp_path / "Family_Portfolio_Report.xlsx"

    resolved_path = export_portfolio_to_excel(
        db_conn=db_conn,
        file_path=output_xlsx,
        cutoff_date="2026-02-28",
        include_closed=True,
    )

    assert resolved_path.is_file()
    assert resolved_path.suffix == ".xlsx"

    # Inspect with openpyxl
    wb = openpyxl.load_workbook(resolved_path)
    sheet_names = wb.sheetnames
    assert "Consolidated Family View" in sheet_names
    assert "Account-Wise Breakdown" in sheet_names

    # Check Tab 1: Consolidated Family View
    ws_fam = wb["Consolidated Family View"]
    assert ws_fam.cell(row=1, column=1).value == "Stock ACB Portfolio Tracker - Consolidated Family View"
    headers_fam = [ws_fam.cell(row=4, column=c).value for c in range(1, 10)]
    assert "Stock Symbol" in headers_fam
    assert "Shares Held" in headers_fam
    assert "Total Buy Cost (₹)" in headers_fam
    assert "Actual Exposure (₹)" in headers_fam
    assert "Booked P&L (₹)" in headers_fam
    assert "Net Exposure (₹)" in headers_fam
    assert "Effective Avg Price (₹)" in headers_fam
    assert "Status / Flag" in headers_fam

    # Verify rows in Tab 1
    symbols_in_fam = [ws_fam.cell(row=r, column=1).value for r in range(5, ws_fam.max_row + 1)]
    assert "INFY" in symbols_in_fam
    assert "RELIANCE" in symbols_in_fam
    assert "FREE_STK" in symbols_in_fam
    assert "DONE_STK" in symbols_in_fam

    # Check Tab 2: Account-Wise Breakdown
    ws_acc = wb["Account-Wise Breakdown"]
    assert ws_acc.cell(row=1, column=1).value == "Stock ACB Portfolio Tracker - Account-Wise Breakdown"
    headers_acc = [ws_acc.cell(row=4, column=c).value for c in range(1, 11)]
    assert "Account Name" in headers_acc
    assert "Stock Symbol" in headers_acc
    assert "Actual Exposure (₹)" in headers_acc
    assert "Booked P&L (₹)" in headers_acc

    # Verify Account Names appear in column 1
    acc_names = [ws_acc.cell(row=r, column=1).value for r in range(5, ws_acc.max_row + 1)]
    assert "Father's Zerodha" in acc_names
    assert "Self Zerodha" in acc_names

    # Check Tab 3: P&L Adjustments & Brokerage
    assert "P&L Adjustments & Brokerage" in sheet_names
    ws_adj = wb["P&L Adjustments & Brokerage"]
    assert "P&L Adjustments & Brokerage Ledger" in ws_adj.cell(row=1, column=1).value
    headers_adj = [ws_adj.cell(row=4, column=c).value for c in range(1, 9)]
    assert "Adjustment ID" in headers_adj
    assert "Stock Symbol" in headers_adj
    assert "Amount (₹)" in headers_adj
    assert "Category" in headers_adj
    assert "Notes" in headers_adj

    # Verify adjustment row in Tab 3
    assert ws_adj.max_row >= 5
    assert ws_adj.cell(row=5, column=2).value == "Self Zerodha"
    assert ws_adj.cell(row=5, column=3).value == "DONE_STK"
    assert ws_adj.cell(row=5, column=6).value == -120.50
    assert ws_adj.cell(row=5, column=8).value == "Q4 DP & AMC"


