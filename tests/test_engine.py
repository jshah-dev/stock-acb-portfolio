"""Unit tests for the House Money analytical math, closed position toggle, and KPI summaries."""

import pytest

from portfolio_tracker.db import init_db, insert_manual_transaction
from portfolio_tracker.engine import get_holdings, get_portfolio_summary


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "engine_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_standard_house_money_reduction(db_conn):
    """Test standard profit sale reducing cost basis:

    Buy 100 shares @ ₹100 = ₹10,000
    Sell 50 shares @ ₹150 = ₹7,500
    Net Qty = 50 shares
    Net Capital at Risk = ₹10,000 - ₹7,500 = ₹2,500
    Effective Avg = ₹2,500 / 50 = ₹50.00/share
    """
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "XYZ", "BUY", 100, 100.0, "2026-01-01 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "XYZ", "SELL", 50, 150.0, "2026-01-15 11:00:00")

    df = get_holdings(db_conn, account_id="ZERODHA_SELF")
    assert len(df) == 1
    row = df.iloc[0]

    assert row["symbol"] == "XYZ"
    assert row["net_qty"] == 50
    assert row["total_buy_cost"] == 10000.0
    assert row["total_proceeds"] == 7500.0
    assert row["net_capital_at_risk"] == 2500.0
    assert row["effective_avg"] == 50.0
    assert row["raw_effective_avg"] == 50.0
    assert bool(row["is_house_money"]) is False
    assert bool(row["is_closed"]) is False
    assert bool(row["is_anomalous"]) is False


def test_pure_house_money_risk_free(db_conn):
    """Test pure house money where capital is fully extracted and remaining shares are risk-free:

    Buy 100 shares @ ₹100 = ₹10,000
    Sell 80 shares @ ₹150 = ₹12,000
    Net Qty = 20 shares
    Net Capital at Risk = ₹10,000 - ₹12,000 = -₹2,000
    Effective Avg (Display) = ₹0.00 (Risk Free)
    Raw Effective Avg (Tooltip) = -₹2,000 / 20 = -₹100.00/share
    Cash Extracted = ₹2,000
    """
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "ABC", "BUY", 100, 100.0, "2026-01-01 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "ABC", "SELL", 80, 150.0, "2026-01-15 11:00:00")

    df = get_holdings(db_conn, account_id="ZERODHA_SELF")
    assert len(df) == 1
    row = df.iloc[0]

    assert row["symbol"] == "ABC"
    assert row["net_qty"] == 20
    assert row["net_capital_at_risk"] == -2000.0
    assert row["effective_avg"] == 0.0
    assert row["raw_effective_avg"] == -100.0
    assert row["cash_extracted"] == 2000.0
    assert bool(row["is_house_money"]) is True
    assert bool(row["is_closed"]) is False


def test_closed_positions_toggle(db_conn):
    """Test closed position (Net Qty == 0) visibility toggle and realized P&L:

    Buy 100 @ ₹100 = ₹10,000
    Sell 100 @ ₹120 = ₹12,000
    Net Qty = 0, Realized P&L = +₹2,000
    """
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "CLOSED_STOCK", "BUY", 100, 100.0, "2026-01-01 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "CLOSED_STOCK", "SELL", 100, 120.0, "2026-01-10 10:00:00")

    # 1. By default include_closed=False: closed stock should be hidden
    df_active_only = get_holdings(db_conn, account_id="ZERODHA_SELF", include_closed=False)
    assert len(df_active_only) == 0

    # 2. When include_closed=True: closed stock is included
    df_with_closed = get_holdings(db_conn, account_id="ZERODHA_SELF", include_closed=True)
    assert len(df_with_closed) == 1
    row = df_with_closed.iloc[0]
    assert row["symbol"] == "CLOSED_STOCK"
    assert row["net_qty"] == 0
    assert bool(row["is_closed"]) is True
    assert row["realized_pnl"] == 2000.0
    assert row["effective_avg"] == 0.0
    assert row["raw_effective_avg"] == 0.0
    assert row["status"] == "CLOSED"


def test_sell_without_buy_anomaly_detection(db_conn):
    """Test flagging of anomalous positions where sell occurs without buy or Net Qty < 0."""
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "MYSTERY_STOCK", "SELL", 50, 100.0, "2026-01-01 10:00:00")

    df = get_holdings(db_conn, account_id="ZERODHA_SELF")
    assert len(df) == 1
    row = df.iloc[0]

    assert row["symbol"] == "MYSTERY_STOCK"
    assert row["net_qty"] == -50
    assert bool(row["is_anomalous"]) is True
    assert "ANOMALOUS" in row["status"]


def test_portfolio_summary_kpis(db_conn):
    """Test executive KPI card computations."""
    # Active stock with risk
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RISK_STOCK", "BUY", 100, 100.0, "2026-01-01")  # Cost: 10,000
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RISK_STOCK", "SELL", 50, 120.0, "2026-01-02")  # Proceeds: 6,000 -> Risk: 4,000

    # Risk-free stock
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "FREE_STOCK", "BUY", 50, 100.0, "2026-01-01")   # Cost: 5,000
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "FREE_STOCK", "SELL", 40, 200.0, "2026-01-02")  # Proceeds: 8,000 -> Risk: -3,000 (Extracted: 3,000)

    # Closed stock
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "DONE_STOCK", "BUY", 10, 50.0, "2026-01-01")    # Cost: 500
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "DONE_STOCK", "SELL", 10, 80.0, "2026-01-02")   # Proceeds: 800 -> PnL: +300

    df = get_holdings(db_conn, account_id="ZERODHA_SELF", include_closed=True)
    kpis = get_portfolio_summary(df)

    assert kpis["total_net_capital_at_risk"] == 4000.0
    assert kpis["total_realized_proceeds"] == 6000.0 + 8000.0 + 800.0
    assert kpis["total_cash_extracted"] == 3000.0 + 300.0
    assert kpis["active_stocks_count"] == 2
    assert kpis["risk_free_stocks_count"] == 1
    assert kpis["closed_stocks_count"] == 1
    assert kpis["anomalous_stocks_count"] == 0
