"""Unit tests for Consolidated Family Pooling vs Individual Account Isolation."""

import pytest

from portfolio_tracker.db import init_db, insert_manual_transaction
from portfolio_tracker.engine import get_holdings


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "consolidation_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_cross_account_pooling_and_individual_isolation(db_conn):
    """Test scenario:

    - Account 1 (ZERODHA_DAD): BUYS 100 shares of RELIANCE @ ₹2000 = ₹200,000
    - Account 2 (ZERODHA_SELF): SELLS 50 shares of RELIANCE @ ₹2500 = ₹125,000

    Expectations:
    1. Account 1 Individual View:
       - Net Qty = 100 shares, Cost = ₹200,000, Proceeds = 0, Net Risk = ₹200,000, Avg = ₹2000.00
    2. Account 2 Individual View:
       - Net Qty = -50 shares, Anomalous (Sell without Buy in this account)
    3. Consolidated Family View (account_id=None):
       - Pooled together: Net Qty = 50 shares
       - Total Buy Cost = ₹200,000
       - Total Proceeds = ₹125,000
       - Net Capital at Risk = ₹75,000
       - Family Effective Avg = ₹75,000 / 50 = ₹1500.00/share!
    """
    insert_manual_transaction(db_conn, "ZERODHA_DAD", "RELIANCE", "BUY", 100, 2000.0, "2026-01-10 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RELIANCE", "SELL", 50, 2500.0, "2026-01-20 11:00:00")

    # 1. Dad's isolated view
    df_dad = get_holdings(db_conn, account_id="ZERODHA_DAD")
    assert len(df_dad) == 1
    assert df_dad.iloc[0]["net_qty"] == 100
    assert df_dad.iloc[0]["net_capital_at_risk"] == 200000.0
    assert df_dad.iloc[0]["effective_avg"] == 2000.0
    assert bool(df_dad.iloc[0]["is_anomalous"]) is False

    # 2. Self isolated view
    df_self = get_holdings(db_conn, account_id="ZERODHA_SELF")
    assert len(df_self) == 1
    assert df_self.iloc[0]["net_qty"] == -50
    assert bool(df_self.iloc[0]["is_anomalous"]) is True

    # 3. Consolidated Family view
    df_family = get_holdings(db_conn, account_id=None)
    assert len(df_family) == 1
    row_fam = df_family.iloc[0]
    assert row_fam["symbol"] == "RELIANCE"
    assert row_fam["net_qty"] == 50
    assert row_fam["total_buy_cost"] == 200000.0
    assert row_fam["total_proceeds"] == 125000.0
    assert row_fam["net_capital_at_risk"] == 75000.0
    assert row_fam["effective_avg"] == 1500.0
    assert bool(row_fam["is_anomalous"]) is False
