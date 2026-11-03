"""Unit tests for the multi-tab formatted Excel export generator."""

from pathlib import Path

import openpyxl
import pytest

from portfolio_tracker.db import (
    init_db,
    insert_dividend,
    insert_manual_transaction,
    insert_pnl_adjustment,
)
from portfolio_tracker.exporter import (
    export_dividends_to_excel,
    export_portfolio_to_excel,
)


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


def test_export_dividends_to_excel_consolidated_and_single(db_conn, tmp_path):
    """Verify that export_dividends_to_excel generates per-account sheets, company totals, and date range headers."""
    # Seed dividend transactions for both accounts
    insert_dividend(db_conn, "ZERODHA_DAD", "INFY", "2025-05-10", 220.0, 10, 22.0)
    insert_dividend(db_conn, "ZERODHA_DAD", "RELIANCE", "2025-07-15", 350.0, 50, 7.0)
    insert_dividend(db_conn, "ZERODHA_SELF", "TCS", "2025-08-20", 500.0, 20, 25.0)

    # 1. Test Consolidated Export
    cons_xlsx = tmp_path / "Consolidated_Dividends.xlsx"
    export_dividends_to_excel(
        db_conn=db_conn,
        file_path=cons_xlsx,
        account_id=None,
        start_date="2025-04-01",
        end_date="2026-03-31",
    )

    wb_cons = openpyxl.load_workbook(cons_xlsx)
    sheet_names = wb_cons.sheetnames

    # Must contain Consolidated Ledger
    assert "Consolidated Ledger" in sheet_names
    # Must contain one sheet per account
    assert "Father's Zerodha" in sheet_names
    assert "Self Zerodha" in sheet_names
    # Must contain Company Wise Total
    assert "Company Wise Total" in sheet_names

    # Check Date Range Banner on Consolidated Ledger
    ws_cons = wb_cons["Consolidated Ledger"]
    subtitle = ws_cons.cell(row=2, column=1).value
    assert "Date Range: 01-04-2025 to 31-03-2026" in subtitle
    assert "Scope: Consolidated (All Accounts)" in subtitle

    # Check Company Wise Total sheet
    ws_comp = wb_cons["Company Wise Total"]
    assert "Dividend Income - Company Wise Total" in ws_comp.cell(row=1, column=1).value
    assert "Date Range: 01-04-2025 to 31-03-2026" in ws_comp.cell(row=2, column=1).value

    # Check columns in Company Wise Total
    comp_headers = [ws_comp.cell(row=4, column=c).value for c in range(1, 5)]
    assert "Company Symbol" in comp_headers
    assert "Total Dividends Received (₹)" in comp_headers
    assert "Contribution (%)" in comp_headers

    # Check that companies appear and total row exists
    comp_syms = [ws_comp.cell(row=r, column=1).value for r in range(5, ws_comp.max_row + 1)]
    assert "INFY" in comp_syms
    assert "RELIANCE" in comp_syms
    assert "TCS" in comp_syms
    assert "TOTAL" in comp_syms

    # 2. Test Single Account Export
    single_xlsx = tmp_path / "Dad_Dividends.xlsx"
    export_dividends_to_excel(
        db_conn=db_conn,
        file_path=single_xlsx,
        account_id="ZERODHA_DAD",
        start_date="2025-04-01",
        end_date="2026-03-31",
    )

    wb_single = openpyxl.load_workbook(single_xlsx)
    single_sheets = wb_single.sheetnames
    assert "Father's Zerodha Ledger" in single_sheets
    assert "Company Wise Total" in single_sheets
    assert "Self Zerodha" not in single_sheets



