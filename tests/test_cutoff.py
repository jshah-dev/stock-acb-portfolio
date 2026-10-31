"""Unit tests for historical cutoff date filtering."""

import pytest

from portfolio_tracker.db import init_db, insert_manual_transaction
from portfolio_tracker.engine import get_holdings


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "cutoff_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_historical_cutoff_date_slices(db_conn):
    """Test portfolio reconstruction at historical points in time:

    Timeline:
    - 2026-01-10: BUY 100 INFY @ ₹1000 (Cost: ₹100,000)
    - 2026-02-15: SELL 50 INFY @ ₹1400 (Proceeds: ₹70,000)
    - 2026-03-20: BUY 20 INFY @ ₹1200 (Cost: ₹24,000)
    """
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 100, 1000.0, "2026-01-10 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "SELL", 50, 1400.0, "2026-02-15 11:30:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 20, 1200.0, "2026-03-20 14:00:00")

    # 1. As of 2026-01-31 (Before the sell):
    df_jan = get_holdings(db_conn, cutoff_date="2026-01-31")
    assert len(df_jan) == 1
    assert df_jan.iloc[0]["net_qty"] == 100
    assert df_jan.iloc[0]["net_capital_at_risk"] == 100000.0
    assert df_jan.iloc[0]["effective_avg"] == 1000.0

    # 2. As of 2026-02-28 (After the sell, before the next buy):
    # Buy: 100,000, Sell: 70,000 -> Risk = 30,000, Qty = 50 -> Avg = 600.0
    df_feb = get_holdings(db_conn, cutoff_date="2026-02-28")
    assert len(df_feb) == 1
    assert df_feb.iloc[0]["net_qty"] == 50
    assert df_feb.iloc[0]["net_capital_at_risk"] == 30000.0
    assert df_feb.iloc[0]["effective_avg"] == 600.0

    # 3. As of 2026-03-31 (After the second buy):
    # Total Buy: 100,000 + 24,000 = 124,000
    # Total Proceeds: 70,000
    # Net Risk: 124,000 - 70,000 = 54,000
    # Net Qty: 50 + 20 = 70
    # Effective Avg: 54,000 / 70 = 771.43
    df_mar = get_holdings(db_conn, cutoff_date="2026-03-31")
    assert len(df_mar) == 1
    assert df_mar.iloc[0]["net_qty"] == 70
    assert df_mar.iloc[0]["net_capital_at_risk"] == 54000.0
    assert df_mar.iloc[0]["effective_avg"] == 771.43

    # 4. As of 2025-12-31 (Before any trades):
    df_empty = get_holdings(db_conn, cutoff_date="2025-12-31")
    assert len(df_empty) == 0

