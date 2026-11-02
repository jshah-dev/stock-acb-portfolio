"""Unit tests for Zerodha tradebook dynamic header detection and idempotent ingestion."""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from portfolio_tracker.db import init_db
from portfolio_tracker.parser import (
    commit_tradebook_records,
    detect_header_row,
    extract_tradebook_records,
    parse_tradebook,
)


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "parser_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def create_sample_csv(file_path: Path, metadata_rows_count: int = 0, include_trade_id: bool = True):
    """Helper to generate mock Zerodha CSV tradebooks with arbitrary metadata header offsets."""
    lines = []
    # Add metadata rows at the top
    for i in range(metadata_rows_count):
        lines.append(f"Report Metadata Line {i+1},Zerodha Console Report,Client ID: XX1234,Date: 2026-01-01")

    # Add header row
    if include_trade_id:
        lines.append("Trade Date,TradingSymbol,Trade Type,Quantity,Price,Trade ID")
    else:
        lines.append("Trade Date,TradingSymbol,Trade Type,Quantity,Price")

    # Add sample trades
    trades = [
        ("2026-01-10 10:15:00", "INFY", "BUY", "100", "1500.50", "TR10001"),
        ("2026-01-12 11:30:00", "TCS", "BUY", "50", "3400.00", "TR10002"),
        ("2026-01-15 14:00:00", "INFY", "SELL", "40", "1650.00", "TR10003"),
        ("2026-01-18 09:45:00", "RELIANCE", "BUY", "25", "2500.00", "TR10004"),
        ("2026-01-20 15:20:00", "HDFCBANK", "BUY", "60", "1600.00", "TR10005"),
    ]

    for t in trades:
        if include_trade_id:
            lines.append(",".join(t))
        else:
            lines.append(",".join(t[:-1]))

    file_path.write_text("\n".join(lines), encoding="utf-8")


def create_sample_excel(file_path: Path, metadata_rows_count: int = 5):
    """Helper to generate mock Zerodha Excel tradebook with metadata rows."""
    data = []
    # Metadata rows
    for i in range(metadata_rows_count):
        data.append([f"Metadata Header {i+1}", "Zerodha Tradebook Export", None, None, None, None])

    # Table Header
    data.append(["Trade Date", "Symbol", "Type", "Qty", "Rate", "Order ID"])

    # Trade rows
    data.append(["2026-02-01 10:00:00", "TATAMOTORS", "BUY", 100, 850.50, 99001])
    data.append(["2026-02-05 11:30:00", "TATAMOTORS", "SELL", 50, 920.00, 99002])
    data.append(["2026-02-10 14:00:00", "ITC", "BUY", 200, 420.00, 99003])

    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, header=False)


def test_detect_header_row_csv(tmp_path):
    """Test dynamic header row detection at offset 0, 5, and 12 rows in CSV."""
    f0 = tmp_path / "tradebook_0.csv"
    create_sample_csv(f0, metadata_rows_count=0)
    assert detect_header_row(f0) == 0

    f5 = tmp_path / "tradebook_5.csv"
    create_sample_csv(f5, metadata_rows_count=5)
    assert detect_header_row(f5) == 5

    f12 = tmp_path / "tradebook_12.csv"
    create_sample_csv(f12, metadata_rows_count=12)
    assert detect_header_row(f12) == 12


def test_detect_header_row_excel(tmp_path):
    """Test dynamic header row detection in Excel files with metadata header."""
    excel_file = tmp_path / "tradebook.xlsx"
    create_sample_excel(excel_file, metadata_rows_count=7)
    assert detect_header_row(excel_file) == 7


def test_parse_tradebook_csv_and_idempotency(db_conn, tmp_path):
    """Verify CSV ingestion and strict deduplication on repeat ingestion."""
    csv_file = tmp_path / "trades.csv"
    create_sample_csv(csv_file, metadata_rows_count=4, include_trade_id=True)

    # First ingestion: all 5 inserted
    inserted, dupes, total = parse_tradebook(csv_file, "ZERODHA_SELF", db_conn)
    assert total == 5
    assert inserted == 5
    assert dupes == 0

    # Verify rows in DB
    rows = db_conn.execute("SELECT symbol, transaction_type, quantity, price FROM transactions ORDER BY trade_date").fetchall()
    assert len(rows) == 5
    assert rows[0]["symbol"] == "INFY"
    assert rows[0]["transaction_type"] == "BUY"
    assert rows[0]["quantity"] == 100
    assert rows[0]["price"] == 1500.50

    # Second ingestion of the EXACT SAME FILE: 0 inserted, 5 duplicates skipped
    inserted2, dupes2, total2 = parse_tradebook(csv_file, "ZERODHA_SELF", db_conn)
    assert total2 == 5
    assert inserted2 == 0
    assert dupes2 == 5

    # Confirm DB row count is still exactly 5
    count = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count == 5


def test_parse_tradebook_excel(db_conn, tmp_path):
    """Verify Excel (.xlsx) ingestion with dynamic header."""
    excel_file = tmp_path / "trades.xlsx"
    create_sample_excel(excel_file, metadata_rows_count=5)

    inserted, dupes, total = parse_tradebook(excel_file, "ZERODHA_DAD", db_conn)
    assert total == 3
    assert inserted == 3
    assert dupes == 0

    rows = db_conn.execute("SELECT symbol, quantity FROM transactions WHERE account_id = 'ZERODHA_DAD' ORDER BY trade_date").fetchall()
    assert len(rows) == 3
    assert rows[0]["symbol"] == "TATAMOTORS"
    assert rows[0]["quantity"] == 100


def test_parse_tradebook_without_trade_ids_fallback_hash(db_conn, tmp_path):
    """Verify that files lacking broker trade IDs generate deterministic SHA-256 IDs and remain idempotent."""
    csv_file = tmp_path / "trades_no_ids.csv"
    create_sample_csv(csv_file, metadata_rows_count=2, include_trade_id=False)

    inserted, dupes, total = parse_tradebook(csv_file, "ZERODHA_SELF", db_conn)
    assert inserted == 5
    assert dupes == 0

    # Verify trade IDs start with HASH_
    trade_ids = [r[0] for r in db_conn.execute("SELECT trade_id FROM transactions;").fetchall()]
    assert all(tid.startswith("HASH_") for tid in trade_ids)

    # Re-ingesting should recognize the deterministic hashes as duplicates
    inserted2, dupes2, total2 = parse_tradebook(csv_file, "ZERODHA_SELF", db_conn)
    assert inserted2 == 0
    assert dupes2 == 5


def test_real_zerodha_tradebook_file(db_conn):
    """Test ingestion with real Zerodha Excel export if present."""
    real_file = Path("test_data/tradebook-FT8594-EQ.xlsx")
    if not real_file.is_file():
        pytest.skip("Real Zerodha file not found")

    assert detect_header_row(real_file) == 14

    inserted, dupes, total = parse_tradebook(real_file, "ZERODHA_SELF", db_conn)
    assert total == 78
    assert inserted == 78
    assert dupes == 0

    # Repeat test for deduplication
    inserted2, dupes2, total2 = parse_tradebook(real_file, "ZERODHA_SELF", db_conn)
    assert total2 == 78
    assert inserted2 == 0
    assert dupes2 == 78


def test_extract_and_commit_tradebook_records(tmp_path, db_conn):
    """Verify 2-phase parsing and insertion for user confirmation workflows."""
    csv_file = tmp_path / "two_phase_trades.csv"
    create_sample_csv(csv_file, metadata_rows_count=1, include_trade_id=True)

    records_to_insert, dupes, total = extract_tradebook_records(csv_file, "ZERODHA_SELF", db_conn)
    assert total == 5
    assert len(records_to_insert) == 5
    assert dupes == 0

    # Before commit, database transactions table should be empty
    count_before = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count_before == 0

    # Commit records
    inserted = commit_tradebook_records(records_to_insert, db_conn)
    assert inserted == 5

    count_after = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count_after == 5



