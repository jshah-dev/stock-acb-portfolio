"""Tests for manual transaction entry, audit listing, and single trade deletion."""

import pytest

from portfolio_tracker.db import (
    delete_transaction,
    get_recent_transactions,
    init_db,
    insert_manual_transaction,
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

    # Invalid price <= 0
    with pytest.raises(ValueError, match="Price must be greater than 0"):
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

