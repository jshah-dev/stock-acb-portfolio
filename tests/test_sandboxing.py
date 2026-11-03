"""Strict sandboxing verification: proves that dividend storage and imports NEVER affect holdings or ACB calculations."""

import pytest

from portfolio_tracker.db import (
    init_db,
    insert_dividend,
    insert_manual_transaction,
)
from portfolio_tracker.engine import get_holdings, get_portfolio_summary


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "sandbox_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_holdings_and_acb_are_strictly_unaffected_by_dividends(db_conn):
    # 1. Setup sample trading activity
    insert_manual_transaction(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="RELIANCE",
        transaction_type="BUY",
        quantity=100,
        price=2000.0,
        trade_date="2025-01-10 10:00:00",
    )
    insert_manual_transaction(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="RELIANCE",
        transaction_type="SELL",
        quantity=50,
        price=2400.0,
        trade_date="2025-02-15 11:00:00",
    )

    # Calculate baseline metrics BEFORE any dividends
    baseline_holdings = get_holdings(db_conn)
    baseline_summary = get_portfolio_summary(baseline_holdings, db_conn)

    assert len(baseline_holdings) == 1
    rel_base = baseline_holdings.iloc[0]
    assert rel_base["symbol"] == "RELIANCE"
    assert rel_base["net_qty"] == 50
    assert rel_base["actual_exposure"] == 100000.0  # 50 * 2000
    assert rel_base["booked_pnl"] == 20000.0        # 50 * (2400 - 2000)
    assert rel_base["net_exposure"] == 80000.0      # 100000 - 20000
    assert baseline_summary["total_actual_exposure"] == 100000.0
    assert baseline_summary["total_net_exposure"] == 80000.0
    assert baseline_summary["total_booked_pnl"] == 20000.0

    # 2. Inject massive dividend records (₹50,000)
    insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="RELIANCE",
        dividend_date="2025-03-01",
        amount=50000.0,
        quantity=50,
        dividend_per_share=1000.0,
    )
    insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_DAD",
        symbol="INFY",
        dividend_date="2025-03-05",
        amount=15000.0,
    )

    # 3. Calculate metrics AFTER dividends
    after_holdings = get_holdings(db_conn)
    after_summary = get_portfolio_summary(after_holdings, db_conn)

    # Assert exact identical values
    assert len(after_holdings) == 1
    rel_after = after_holdings.iloc[0]
    assert rel_after["symbol"] == rel_base["symbol"]
    assert rel_after["net_qty"] == rel_base["net_qty"]
    assert rel_after["actual_exposure"] == rel_base["actual_exposure"]
    assert rel_after["booked_pnl"] == rel_base["booked_pnl"]
    assert rel_after["net_exposure"] == rel_base["net_exposure"]
    assert rel_after["effective_avg"] == rel_base["effective_avg"]
    assert rel_after["is_house_money"] == rel_base["is_house_money"]

    assert after_summary["total_actual_exposure"] == baseline_summary["total_actual_exposure"]
    assert after_summary["total_net_exposure"] == baseline_summary["total_net_exposure"]
    assert after_summary["total_booked_pnl"] == baseline_summary["total_booked_pnl"]
    assert after_summary["total_net_realized_pnl"] == baseline_summary["total_net_realized_pnl"]
    assert after_summary["active_stocks_count"] == baseline_summary["active_stocks_count"]


def test_opt_in_dividend_risk_deduction_and_house_money(db_conn):
    """Test opt-in dividend deduction from capital at risk and house money transition."""
    # 1. Setup trade: Buy 100 @ 1000, Sell 50 @ 1200
    insert_manual_transaction(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        symbol="TCS",
        transaction_type="BUY",
        quantity=100,
        price=1000.0,
        trade_date="2025-01-10",
    )
    insert_manual_transaction(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        symbol="TCS",
        transaction_type="SELL",
        quantity=50,
        price=1200.0,
        trade_date="2025-02-15",
    )
    # Remaining: 50 shares @ 1000 buy avg = Actual: 50,000, Booked P&L: 10,000. Net Exposure: 40,000.

    # 2. Insert dividend of 15,000
    insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        symbol="TCS",
        dividend_date="2025-03-01",
        amount=15000.0,
        quantity=50,
        dividend_per_share=300.0,
    )

    # When include_dividends=False: baseline Net Exposure remains 40,000
    df_no_div = get_holdings(db_conn, include_dividends=False)
    assert df_no_div.iloc[0]["net_exposure"] == 40000.0
    assert df_no_div.iloc[0]["dividend_received"] == 0.0

    # When include_dividends=True: Net Exposure = 50,000 - (10,000 + 15,000) = 25,000
    df_div = get_holdings(db_conn, include_dividends=True)
    row = df_div.iloc[0]
    assert row["symbol"] == "TCS"
    assert row["actual_exposure"] == 50000.0
    assert row["booked_pnl"] == 10000.0
    assert row["dividend_received"] == 15000.0
    assert row["net_exposure"] == 25000.0
    assert row["effective_avg"] == 500.0  # 25,000 / 50
    assert bool(row["is_house_money"]) is False

    summary = get_portfolio_summary(df_div, db_conn=db_conn, include_dividends=True)
    assert summary["total_net_exposure"] == 25000.0
    assert summary["total_dividends_received"] == 15000.0

    # 3. Insert additional dividend of 30,000 (total dividends = 45,000)
    # Net Diff = 50,000 - (10,000 + 45,000) = -5,000 <= 0 -> RISK_FREE (House Money)
    insert_dividend(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        symbol="TCS",
        dividend_date="2025-04-01",
        amount=30000.0,
        quantity=50,
        dividend_per_share=600.0,
    )

    df_house = get_holdings(db_conn, include_dividends=True)
    row_hm = df_house.iloc[0]
    assert row_hm["dividend_received"] == 45000.0
    assert row_hm["net_exposure"] == 0.0
    assert row_hm["effective_avg"] == 0.0
    assert row_hm["raw_effective_avg"] == -100.0  # -5,000 / 50
    assert row_hm["cash_extracted"] == 5000.0
    assert bool(row_hm["is_house_money"]) is True
    assert row_hm["status"] == "RISK_FREE (House Money)"

    summary_hm = get_portfolio_summary(df_house, db_conn=db_conn, include_dividends=True)
    assert summary_hm["total_net_exposure"] == 0.0
    assert summary_hm["total_dividends_received"] == 45000.0
    assert summary_hm["risk_free_stocks_count"] == 1
