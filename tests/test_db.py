"""Tests for database initialization, schema integrity, and live backup/restore."""

import sqlite3
from pathlib import Path

import pytest

from portfolio_tracker.db import (
    backup_database,
    get_connection,
    init_db,
    restore_database,
)


@pytest.fixture
def test_db_path(tmp_path):
    """Fixture providing a fresh database path for each test."""
    return tmp_path / "test_portfolio.db"


def test_init_db_creates_tables_and_seeds_defaults(test_db_path):
    """Verify init_db creates tables, indexes, and starter accounts."""
    conn = init_db(test_db_path)

    # Check WAL and foreign keys
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1

    # Check tables exist
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
    ]
    assert "accounts" in tables
    assert "transactions" in tables

    # Check initial seeds
    accounts = conn.execute("SELECT account_id, user_name FROM accounts ORDER BY account_id;").fetchall()
    acc_map = {row["account_id"]: row["user_name"] for row in accounts}
    assert "ZERODHA_DAD" in acc_map
    assert "ZERODHA_SELF" in acc_map
    assert acc_map["ZERODHA_DAD"] == "Father's Zerodha"
    assert acc_map["ZERODHA_SELF"] == "Self Zerodha"

    conn.close()


def test_backup_and_restore(test_db_path, tmp_path):
    """Verify live database backup and restore operations."""
    conn = init_db(test_db_path)

    # Insert test account
    conn.execute(
        "INSERT INTO accounts (account_id, user_name, broker) VALUES ('ACC_TEST', 'Test Acc', 'Zerodha');"
    )
    conn.commit()

    # Backup to external file
    backup_file = tmp_path / "backup_archive.db"
    backup_database(conn, backup_file)
    assert backup_file.exists()

    conn.close()

    # Restore to a fresh location
    restored_db_path = tmp_path / "restored.db"
    restore_database(backup_file, restored_db_path)
    assert restored_db_path.exists()

    # Verify restored contents
    restored_conn = get_connection(restored_db_path)
    row = restored_conn.execute(
        "SELECT user_name FROM accounts WHERE account_id = 'ACC_TEST';"
    ).fetchone()
    assert row is not None
    assert row["user_name"] == "Test Acc"
    restored_conn.close()

