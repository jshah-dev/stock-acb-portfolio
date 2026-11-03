"""Unit tests for dividends database schema, cascades, and aggregation queries."""

import sqlite3
import pytest

from portfolio_tracker.db import (
    add_account,
    add_symbol_mapping,
    delete_account,
    delete_dividend,
    get_all_symbols,
    get_dividend,
    get_dividends,
    get_dividends_summary,
    init_db,
    insert_dividend,
    update_account,
    update_dividend,
)


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "dividends_db_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_insert_and_get_dividend(db_conn):
    div_id = insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="INFY",
        dividend_date="2025-06-15",
        amount=220.0,
        quantity=10,
        dividend_per_share=22.0,
        remarks="Test dividend",
    )
    assert div_id.startswith("DIV_MANUAL_ZERODHA_DAD_")

    row = get_dividend(db_conn, div_id)
    assert row is not None
    assert row["symbol"] == "INFY"
    assert row["amount"] == 220.0
    assert row["quantity"] == 10
    assert row["dividend_per_share"] == 22.0
    assert row["user_name"] == "Father's Zerodha"


def test_update_and_delete_dividend(db_conn):
    div_id = insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="TCS",
        dividend_date="2025-07-20",
        amount=500.0,
    )
    # Update
    ok = update_dividend(
        conn=db_conn,
        dividend_id=div_id,
        account_id="ZERODHA_DAD",
        symbol="TCS",
        dividend_date="2025-07-21",
        amount=550.0,
        remarks="Updated amount",
    )
    assert ok is True

    updated = get_dividend(db_conn, div_id)
    assert updated["amount"] == 550.0
    assert updated["remarks"] == "Updated amount"

    # Delete
    deleted = delete_dividend(db_conn, div_id)
    assert deleted is True
    assert get_dividend(db_conn, div_id) is None


def test_account_cascade_and_rename(db_conn):
    # Add a custom account
    add_account(db_conn, "ACC_TEMP", "Temporary Account")
    div_id = insert_dividend(db_conn, "ACC_TEMP", "RELIANCE", "2025-08-01", 300.0)

    # Rename account
    update_account(db_conn, "ACC_TEMP", "ACC_PERM", "Permanent Account")
    div_row = get_dividend(db_conn, div_id)
    assert div_row["account_id"] == "ACC_PERM"
    assert div_row["user_name"] == "Permanent Account"

    # Delete account -> cascades delete of dividend
    delete_account(db_conn, "ACC_PERM")
    assert get_dividend(db_conn, div_id) is None


def test_symbol_mapping_on_dividends(db_conn):
    # Map CADILAHC -> ZYDUSLIFE
    add_symbol_mapping(db_conn, "CADILAHC", "ZYDUSLIFE")

    insert_dividend(db_conn, "ZERODHA_DAD", "CADILAHC", "2025-04-10", 150.0)
    divs = get_dividends(db_conn, symbol="ZYDUSLIFE")
    assert len(divs) == 1
    assert divs[0]["original_symbol"] == "CADILAHC"
    assert divs[0]["canonical_symbol"] == "ZYDUSLIFE"
    assert divs[0]["is_mapped"] == 1


def test_dividends_summary_and_fy_breakdown(db_conn):
    insert_dividend(db_conn, "ZERODHA_DAD", "INFY", "2025-05-15", 200.0)  # FY 2025-26
    insert_dividend(db_conn, "ZERODHA_DAD", "TCS", "2025-08-20", 300.0)   # FY 2025-26
    insert_dividend(db_conn, "ZERODHA_SELF", "INFY", "2024-11-10", 150.0) # FY 2024-25

    # Consolidated summary
    s_all = get_dividends_summary(db_conn)
    assert s_all["total_amount"] == 650.0
    assert s_all["payout_count"] == 3
    assert s_all["unique_companies"] == 2
    assert s_all["top_payer"]["symbol"] == "INFY"
    assert s_all["top_payer"]["amount"] == 350.0
    assert s_all["fy_totals"]["FY 2025-26"] == 500.0
    assert s_all["fy_totals"]["FY 2024-25"] == 150.0

    # Filtered by account
    s_self = get_dividends_summary(db_conn, account_id="ZERODHA_SELF")
    assert s_self["total_amount"] == 150.0
    assert s_self["payout_count"] == 1


def test_symbols_autocomplete_includes_dividends(db_conn):
    insert_dividend(db_conn, "ZERODHA_DAD", "SPECIALDIVSYM", "2025-09-01", 100.0)
    syms = get_all_symbols(db_conn)
    assert "SPECIALDIVSYM" in syms

