"""Tests for manual transaction entry, audit listing, and single trade deletion."""

import pytest

from portfolio_tracker.db import (
    delete_transaction,
    get_recent_transactions,
    get_transaction,
    init_db,
    insert_manual_transaction,
    update_transaction,
)


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "manual_trades_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_insert_manual_transaction_validations(db_conn):
    """Verify validation rules on manual entries."""
    # Invalid transaction type
    with pytest.raises(ValueError, match="BUY' or 'SELL"):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "INFY", "HOLD", 10, 1500.0, "2026-01-01 10:00:00"
        )

    # Invalid quantity <= 0
    with pytest.raises(ValueError, match="Quantity must be greater than 0"):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "INFY", "BUY", 0, 1500.0, "2026-01-01 10:00:00"
        )

    # Invalid price < 0
    with pytest.raises(ValueError, match="Price cannot be negative"):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "INFY", "BUY", 10, -50.0, "2026-01-01 10:00:00"
        )

    # Empty symbol
    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "   ", "BUY", 10, 1500.0, "2026-01-01 10:00:00"
        )


def test_insert_manual_transaction_and_audit(db_conn):
    """Verify manual transaction gets unique MANUAL_ prefix and appears in audit."""
    trade_id = insert_manual_transaction(
        db_conn,
        account_id="ZERODHA_SELF",
        symbol="reliance",
        transaction_type="buy",
        quantity=50,
        price=2450.75,
        trade_date="2026-02-10 14:15:00",
        notes="Bonus issue adjustment",
    )

    assert trade_id.startswith("MANUAL_ZERODHA_SELF_")

    # Verify audit query
    recent = get_recent_transactions(db_conn)
    assert len(recent) == 1
    item = recent[0]
    assert item["trade_id"] == trade_id
    assert item["symbol"] == "RELIANCE"  # Auto-uppercased
    assert item["transaction_type"] == "BUY"
    assert item["quantity"] == 50
    assert item["price"] == 2450.75
    assert item["notes"] == "Bonus issue adjustment"
    assert item["user_name"] == "Self Zerodha"


def test_delete_single_transaction(db_conn):
    """Verify deleting a single transaction without deleting the entire account."""
    trade_id_1 = insert_manual_transaction(
        db_conn, "ZERODHA_SELF", "TCS", "BUY", 10, 3500.0, "2026-01-01 10:00:00"
    )
    trade_id_2 = insert_manual_transaction(
        db_conn, "ZERODHA_SELF", "INFY", "BUY", 20, 1500.0, "2026-01-02 10:00:00"
    )

    assert len(get_recent_transactions(db_conn)) == 2

    # Delete trade 1
    deleted = delete_transaction(db_conn, trade_id_1)
    assert deleted is True

    # Check only trade 2 remains
    remaining = get_recent_transactions(db_conn)
    assert len(remaining) == 1
    assert remaining[0]["trade_id"] == trade_id_2

    # Attempting to delete non-existent returns False
    assert delete_transaction(db_conn, "NON_EXISTENT") is False


def test_get_and_update_transaction(db_conn):
    """Verify fetching and updating transaction details (e.g. for split/bonus corporate actions)."""
    trade_id = insert_manual_transaction(
        db_conn, "ZERODHA_SELF", "TCS", "BUY", 50, 3200.0, "2024-01-15 10:00:00", notes="Initial buy"
    )

    # 1. Fetch single trade
    t = get_transaction(db_conn, trade_id)
    assert t is not None
    assert t["trade_id"] == trade_id
    assert t["symbol"] == "TCS"
    assert t["quantity"] == 50
    assert t["price"] == 3200.0
    assert t["user_name"] == "Self Zerodha"

    # 2. Validation failures on update
    with pytest.raises(ValueError, match="Quantity must be greater than 0"):
        update_transaction(db_conn, trade_id, "ZERODHA_SELF", "TCS", "BUY", 0, 1600.0, "2024-01-15 10:00:00")

    with pytest.raises(ValueError, match="Price cannot be negative"):
        update_transaction(db_conn, trade_id, "ZERODHA_SELF", "TCS", "BUY", 100, -10.0, "2024-01-15 10:00:00")

    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        update_transaction(db_conn, trade_id, "ZERODHA_SELF", "  ", "BUY", 100, 1600.0, "2024-01-15 10:00:00")

    with pytest.raises(ValueError, match="BUY' or 'SELL"):
        update_transaction(db_conn, trade_id, "ZERODHA_SELF", "TCS", "HOLD", 100, 1600.0, "2024-01-15 10:00:00")

    # 3. Simulate 1:2 Stock Split (Quantity doubles 50 -> 100, Price halves 3200 -> 1600)
    updated = update_transaction(
        db_conn,
        trade_id=trade_id,
        account_id="ZERODHA_SELF",
        symbol="TCS",
        transaction_type="BUY",
        quantity=100,
        price=1600.0,
        trade_date="2024-01-15 00:00:00",
        notes="Stock Split 1:2 adjustment",
    )
    assert updated is True

    # 4. Verify updated values
    t_after = get_transaction(db_conn, trade_id)
    assert t_after["quantity"] == 100
    assert t_after["price"] == 1600.0
    assert t_after["notes"] == "Stock Split 1:2 adjustment"

    # Total capital cost stays preserved: 50 * 3200 == 100 * 1600 == 160,000
    assert t["quantity"] * t["price"] == t_after["quantity"] * t_after["price"]

    # 5. Non-existent trade_id returns False
    assert update_transaction(db_conn, "NON_EXISTENT", "ZERODHA_SELF", "TCS", "BUY", 10, 100.0, "2024-01-15") is False


def test_bonus_trade_zero_rupees_manual_and_update(db_conn):
    """Verify bonus shares with price = 0.00 succeed in insert and update."""
    bonus_id = insert_manual_transaction(
        conn=db_conn,
        account_id="ZERODHA_SELF",
        symbol="WIPRO",
        transaction_type="BUY",
        quantity=100,
        price=0.0,
        trade_date="2025-06-01 00:00:00",
        notes="1:1 Bonus Shares credited",
    )
    assert bonus_id.startswith("MANUAL_ZERODHA_SELF_")
    t = get_transaction(db_conn, bonus_id)
    assert t["symbol"] == "WIPRO"
    assert t["quantity"] == 100
    assert t["price"] == 0.0
    assert t["notes"] == "1:1 Bonus Shares credited"

    # Also test update to zero price
    updated = update_transaction(
        conn=db_conn,
        trade_id=bonus_id,
        account_id="ZERODHA_SELF",
        symbol="WIPRO",
        transaction_type="BUY",
        quantity=150,
        price=0.0,
        trade_date="2025-06-01 00:00:00",
        notes="Adjusted bonus quantity to 150",
    )
    assert updated is True
    t_after = get_transaction(db_conn, bonus_id)
    assert t_after["quantity"] == 150
    assert t_after["price"] == 0.0



