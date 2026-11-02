"""Tests for account lifecycle management and foreign key cascade deletions."""

import pytest

from portfolio_tracker.db import (
    add_account,
    delete_account,
    get_account_transaction_count,
    get_accounts,
    init_db,
    insert_manual_transaction,
    update_account,
)


@pytest.fixture
def db_conn(tmp_path):
    """Fixture providing a fresh in-memory or temporary database connection."""
    test_db = tmp_path / "accounts_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_add_and_list_accounts(db_conn):
    """Verify adding family accounts and listing them with transaction counts."""
    # Check default 2 accounts
    initial = get_accounts(db_conn)
    assert len(initial) == 2

    # Add mother's account
    added = add_account(db_conn, "ZERODHA_MOM", "Mother's Zerodha", "Zerodha")
    assert added["account_id"] == "ZERODHA_MOM"
    assert added["user_name"] == "Mother's Zerodha"

    updated = get_accounts(db_conn)
    assert len(updated) == 3
    ids = [acc["account_id"] for acc in updated]
    assert "ZERODHA_MOM" in ids


def test_delete_account_cascade(db_conn):
    """Verify deleting an account cascades to delete its transactions."""
    # Add a 3rd account
    add_account(db_conn, "ZERODHA_MOM", "Mother's Zerodha")

    # Add 2 transactions to ZERODHA_MOM
    insert_manual_transaction(
        db_conn,
        account_id="ZERODHA_MOM",
        symbol="TCS",
        transaction_type="BUY",
        quantity=10,
        price=3500.0,
        trade_date="2026-01-15 10:00:00",
    )
    insert_manual_transaction(
        db_conn,
        account_id="ZERODHA_MOM",
        symbol="INFY",
        transaction_type="BUY",
        quantity=25,
        price=1500.0,
        trade_date="2026-01-20 11:30:00",
    )

    assert get_account_transaction_count(db_conn, "ZERODHA_MOM") == 2

    # Delete ZERODHA_MOM
    deleted_tx_count = delete_account(db_conn, "ZERODHA_MOM")
    assert deleted_tx_count == 2

    # Verify account is gone
    accounts = get_accounts(db_conn)
    assert "ZERODHA_MOM" not in [a["account_id"] for a in accounts]

    # Verify cascaded deletion of transactions
    count = db_conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = 'ZERODHA_MOM';"
    ).fetchone()[0]
    assert count == 0


def test_cannot_delete_last_remaining_account(db_conn):
    """Verify safeguard prevents deleting the only remaining account."""
    # Start with 2 default accounts, delete one
    delete_account(db_conn, "ZERODHA_DAD")
    assert len(get_accounts(db_conn)) == 1

    # Attempting to delete the last account must raise ValueError
    with pytest.raises(ValueError, match="Cannot delete the only remaining account"):
        delete_account(db_conn, "ZERODHA_SELF")


def test_update_account(db_conn):
    """Verify updating account ID and description, including transaction foreign key cascade."""
    # 1. Update display name & broker for existing account
    update_account(
        db_conn,
        old_account_id="ZERODHA_SELF",
        new_account_id="ZERODHA_SELF",
        new_user_name="Primary Trader (Self)",
        new_broker="Groww",
    )
    accounts = {a["account_id"]: a for a in get_accounts(db_conn)}
    assert accounts["ZERODHA_SELF"]["user_name"] == "Primary Trader (Self)"
    assert accounts["ZERODHA_SELF"]["broker"] == "Groww"

    # 2. Add a transaction under ZERODHA_SELF
    trade_id = insert_manual_transaction(
        db_conn,
        account_id="ZERODHA_SELF",
        symbol="INFY",
        transaction_type="BUY",
        quantity=50,
        price=1400.0,
        trade_date="2026-01-10 10:00:00",
    )
    assert get_account_transaction_count(db_conn, "ZERODHA_SELF") == 1

    # 3. Rename Account ID: ZERODHA_SELF -> MASTER_PORTFOLIO
    update_account(
        db_conn,
        old_account_id="ZERODHA_SELF",
        new_account_id="MASTER_PORTFOLIO",
        new_user_name="Master Portfolio",
        new_broker="Zerodha",
    )

    # Old ID should not exist
    all_accounts = {a["account_id"]: a for a in get_accounts(db_conn)}
    assert "ZERODHA_SELF" not in all_accounts
    assert "MASTER_PORTFOLIO" in all_accounts
    assert all_accounts["MASTER_PORTFOLIO"]["user_name"] == "Master Portfolio"

    # Transactions should now be pointed to MASTER_PORTFOLIO
    assert get_account_transaction_count(db_conn, "MASTER_PORTFOLIO") == 1
    tx_row = db_conn.execute("SELECT account_id FROM transactions WHERE trade_id = ?;", (trade_id,)).fetchone()
    assert tx_row[0] == "MASTER_PORTFOLIO"

    # 4. Error validations
    with pytest.raises(ValueError, match="already in use"):
        update_account(db_conn, "MASTER_PORTFOLIO", "ZERODHA_DAD", "Duplicate Name")

    with pytest.raises(ValueError, match="does not exist"):
        update_account(db_conn, "NON_EXISTENT", "NEW_NAME", "Desc")

    with pytest.raises(ValueError, match="Display Name / Description cannot be empty"):
        update_account(db_conn, "MASTER_PORTFOLIO", "MASTER_PORTFOLIO", "   ")


