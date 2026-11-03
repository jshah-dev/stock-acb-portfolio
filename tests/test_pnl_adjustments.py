"""Tests for P&L Adjustments, Carried-Forward Profits/Losses, and Brokerage Charges."""

import pytest
from datetime import datetime

from portfolio_tracker.db import (
    add_account,
    delete_account,
    delete_pnl_adjustment,
    get_adjustments_summary,
    get_pnl_adjustment,
    get_pnl_adjustments,
    insert_manual_transaction,
    insert_pnl_adjustment,
    update_account,
    update_pnl_adjustment,
)
from portfolio_tracker.engine import get_holdings, get_portfolio_summary


def test_insert_and_get_pnl_adjustments(db_conn):
    """Verify insertion and querying of stock-specific adjustments."""
    # 1. Insert carried forward profit from an untracked old account on INFY
    adj_id1 = insert_pnl_adjustment(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        amount=50000.0,
        adjustment_date="2023-01-15 10:00:00",
        category="CARRIED_FORWARD_PROFIT",
        symbol="INFY",
        notes="Historical profit FY21-22 from Old Angel Demat",
    )
    assert adj_id1.startswith("ADJ_PROFIT_")

    # 2. Insert stock-specific brokerage charge on TCS
    adj_id2 = insert_pnl_adjustment(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        amount=150.0,
        adjustment_date="2023-02-10 12:00:00",
        category="BROKERAGE_CHARGES",
        symbol="TCS",
        notes="Brokerage on TCS swing trade",
    )
    assert adj_id2.startswith("ADJ_LOSS_")

    # 3. Query all adjustments
    all_adjs = get_pnl_adjustments(db_conn)
    assert len(all_adjs) == 2
    # Verify chronological ordering descending
    assert all_adjs[0]["adjustment_id"] == adj_id2  # Feb 2023
    assert all_adjs[1]["adjustment_id"] == adj_id1  # Jan 2023

    # 4. Query by symbol
    tcs_adjs = get_pnl_adjustments(db_conn, symbol="TCS")
    assert len(tcs_adjs) == 1
    assert tcs_adjs[0]["adjustment_id"] == adj_id2
    assert tcs_adjs[0]["signed_amount"] == -150.0

    # 5. Query by cutoff date
    past_adjs = get_pnl_adjustments(db_conn, cutoff_date="2023-01-31")
    assert len(past_adjs) == 1
    assert past_adjs[0]["adjustment_id"] == adj_id1


def test_pnl_adjustments_crud_validation(db_conn):
    """Verify validation rules, update, and deletion of adjustments."""
    # Missing symbol should fail
    with pytest.raises(ValueError, match="stock symbol is required"):
        insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 100.0, "2024-01-01", "BROKERAGE_CHARGES", symbol=None)

    # Negative amount should fail
    with pytest.raises(ValueError, match="greater than 0"):
        insert_pnl_adjustment(db_conn, "ZERODHA_SELF", -100.0, "2024-01-01", "BROKERAGE_CHARGES", symbol="TCS")

    # Zero amount should fail
    with pytest.raises(ValueError, match="greater than 0"):
        insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 0.0, "2024-01-01", "BROKERAGE_CHARGES", symbol="TCS")

    # Invalid category should fail
    with pytest.raises(ValueError, match="Invalid category"):
        insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 500.0, "2024-01-01", "INVALID_CAT", symbol="TCS")

    # Insert valid entry
    adj_id = insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=15.93,
        adjustment_date="2024-03-01",
        category="BROKERAGE_CHARGES",
        symbol="INFY",
        notes="Brokerage charge",
    )

    # Get single adjustment
    adj = get_pnl_adjustment(db_conn, adj_id)
    assert adj is not None
    assert adj["amount"] == 15.93
    assert adj["category"] == "BROKERAGE_CHARGES"
    assert adj["direction"] == "LOSS"
    assert adj["signed_amount"] == -15.93

    # Update adjustment
    success = update_pnl_adjustment(
        db_conn,
        adjustment_id=adj_id,
        account_id="ZERODHA_SELF",
        amount=20.0,
        adjustment_date="2024-03-02",
        category="BROKERAGE_CHARGES",
        direction="LOSS",
        symbol="INFY",
        notes="Updated brokerage charge",
    )
    assert success is True
    updated = get_pnl_adjustment(db_conn, adj_id)
    assert updated["amount"] == 20.0
    assert updated["notes"] == "Updated brokerage charge"

    # Delete adjustment
    assert delete_pnl_adjustment(db_conn, adj_id) is True
    assert get_pnl_adjustment(db_conn, adj_id) is None


def test_adjustments_summary_calculation(db_conn):
    """Verify aggregate summary statistics across carried profit, carried loss, and brokerage."""
    insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 100000.0, "2024-01-01", "CARRIED_FORWARD_PROFIT", symbol="TCS")
    insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 15000.0, "2024-01-02", "CARRIED_FORWARD_LOSS", symbol="INFY")
    insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 2500.0, "2024-01-03", "BROKERAGE_CHARGES", symbol="RELIANCE")

    summary = get_adjustments_summary(db_conn, account_id="ZERODHA_SELF")
    assert summary["total_carried_profit"] == 100000.0
    assert summary["total_carried_loss"] == 15000.0
    assert summary["total_brokerage"] == 2500.0
    # Net = 100,000 - (15,000 + 2,500) = 82,500.0
    assert summary["net_adjustments"] == 82500.0
    assert summary["adjustments_count"] == 3


def test_account_cascade_and_rename_adjustments(db_conn):
    """Verify that updating account ID cascades to adjustments, and deleting account removes adjustments."""
    add_account(db_conn, "TEST_ACC", "Test User", "Zerodha")
    adj_id = insert_pnl_adjustment(db_conn, "TEST_ACC", 5000.0, "2024-01-01", "CARRIED_FORWARD_PROFIT", symbol="TCS")

    # Update account ID from TEST_ACC to RENAMED_ACC
    update_account(db_conn, "TEST_ACC", "RENAMED_ACC", "Renamed User", "Zerodha")
    adj = get_pnl_adjustment(db_conn, adj_id)
    assert adj["account_id"] == "RENAMED_ACC"

    # Delete account: should cascade delete the adjustment
    delete_account(db_conn, "RENAMED_ACC")
    assert get_pnl_adjustment(db_conn, adj_id) is None


def test_stock_specific_adjustment_house_money_integration(db_conn):
    """Verify that forwarding profit on a stock directly lowers Net Exposure and achieves Risk-Free status."""
    # Buy 10 shares of RELIANCE @ 2500 -> Actual Exposure = 25,000
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RELIANCE", "BUY", 10, 2500.0, "2024-01-01")

    # Before adjustment: Net Exposure = 25,000, Booked P&L = 0, is_house_money = False
    df_before = get_holdings(db_conn)
    row_before = df_before[df_before["symbol"] == "RELIANCE"].iloc[0]
    assert row_before["actual_exposure"] == 25000.0
    assert row_before["booked_pnl"] == 0.0
    assert row_before["net_exposure"] == 25000.0
    assert bool(row_before["is_house_money"]) is False

    # Forward 30,000 profit on RELIANCE from an old untracked broker account
    insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=30000.0,
        adjustment_date="2023-12-31",
        category="CARRIED_FORWARD_PROFIT",
        symbol="RELIANCE",
        notes="Historical profit on RELIANCE from old account",
    )

    # After adjustment:
    # Booked P&L = 0 + 30,000 = 30,000
    # Net Exposure = max(0, 25,000 - 30,000) = 0.0 -> Pure House Money!
    df_after = get_holdings(db_conn)
    row_after = df_after[df_after["symbol"] == "RELIANCE"].iloc[0]
    assert row_after["actual_exposure"] == 25000.0
    assert row_after["booked_pnl"] == 30000.0
    assert row_after["trade_booked_pnl"] == 0.0
    assert row_after["stock_carried_profit"] == 30000.0
    assert row_after["net_exposure"] == 0.0
    assert bool(row_after["is_house_money"]) is True
    assert row_after["status"] == "RISK_FREE (House Money)"

    # Add a ₹500 brokerage charge on RELIANCE
    insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=500.0,
        adjustment_date="2024-01-10",
        category="BROKERAGE_CHARGES",
        symbol="RELIANCE",
    )

    df_charge = get_holdings(db_conn)
    row_charge = df_charge[df_charge["symbol"] == "RELIANCE"].iloc[0]
    # Booked P&L is now 30,000 - 500 = 29,500
    assert row_charge["booked_pnl"] == 29500.0
    assert row_charge["stock_charges"] == 500.0
    # Net Exposure = max(0, 25,000 - 29,500) = 0.0 (still house money)
    assert row_charge["net_exposure"] == 0.0


def test_portfolio_summary_with_adjustments(db_conn):
    """Verify that get_portfolio_summary aggregates trade profits, carried P&L, and charges."""
    # Trade: Buy 100 INFY @ 1000, Sell 50 @ 1500 -> Trade Booked P&L = 50 * 500 = 25,000
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 100, 1000.0, "2024-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "SELL", 50, 1500.0, "2024-01-15")

    # Carried profit from old account on INFY: +50,000
    insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 50000.0, "2024-01-02", "CARRIED_FORWARD_PROFIT", symbol="INFY")
    # Brokerage charges on INFY: -2,000
    insert_pnl_adjustment(db_conn, "ZERODHA_SELF", 2000.0, "2024-01-10", "BROKERAGE_CHARGES", symbol="INFY")

    df = get_holdings(db_conn)
    summary = get_portfolio_summary(df, db_conn=db_conn)

    assert summary["total_trade_booked_pnl"] == 25000.0
    assert summary["total_carried_profit"] == 50000.0
    assert summary["total_brokerage"] == 2000.0
    assert summary["total_net_adjustments"] == 48000.0  # 50,000 - 2,000
    # Net Realized P&L = 25,000 + 48,000 = 73,000
    assert summary["total_net_realized_pnl"] == 73000.0
    assert summary["adjustments_count"] == 2


def test_source_reference_column_dropped_and_migrated(tmp_path):
    """Verify that source_reference is absent from pnl_adjustments and legacy tables migrate smoothly."""
    from portfolio_tracker.db import init_db

    db_file = tmp_path / "legacy_test.db"
    conn = init_db(db_file)

    # 1. Verify schema does not have source_reference
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pnl_adjustments);").fetchall()]
    assert "source_reference" not in cols
    assert "notes" in cols
    assert "symbol" in cols
    assert "amount" in cols

    # 2. Simulate legacy table with source_reference column
    conn.execute("ALTER TABLE pnl_adjustments ADD COLUMN source_reference TEXT;")
    cols_with_ref = [r[1] for r in conn.execute("PRAGMA table_info(pnl_adjustments);").fetchall()]
    assert "source_reference" in cols_with_ref

    # Insert a record using raw SQL with source_reference populated
    conn.execute("""
        INSERT INTO pnl_adjustments 
        (adjustment_id, account_id, symbol, adjustment_date, category, direction, amount, source_reference, notes)
        VALUES ('ADJ_LEGACY_01', 'ZERODHA_SELF', 'INFY', '2024-01-01 10:00:00', 'CARRIED_FORWARD_PROFIT', 'PROFIT', 1000.0, 'Legacy Broker', 'Old notes');
    """)
    conn.commit()
    conn.close()

    # Re-run init_db on the database to trigger automatic migration
    conn2 = init_db(db_file)
    cols_after_mig = [r[1] for r in conn2.execute("PRAGMA table_info(pnl_adjustments);").fetchall()]
    assert "source_reference" not in cols_after_mig

    # Verify data was preserved
    row = conn2.execute("SELECT adjustment_id, amount, notes FROM pnl_adjustments WHERE adjustment_id = 'ADJ_LEGACY_01';").fetchone()
    assert row is not None
    assert row["amount"] == 1000.0
    assert row["notes"] == "Old notes"
    conn2.close()

