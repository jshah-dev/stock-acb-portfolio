"""Unit tests for Zerodha dividend parser with dynamic headers, symbol cleaning, and deduplication."""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from portfolio_tracker.db import init_db
from portfolio_tracker.dividend_parser import (
    clean_dividend_symbol,
    detect_dividend_header_row,
    extract_client_id_from_metadata,
    extract_dividend_records,
    parse_dividend_file,
)


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "dividend_parser_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def create_sample_dividend_csv(file_path: Path, metadata_rows_count: int = 0):
    lines = []
    for i in range(metadata_rows_count):
        lines.append(f"Metadata Line {i+1},Client ID,FT8594,Financial Year: 2025-26")

    lines.append("Symbol,Ex-date,Qty,Dividend per share,Total dividend")
    lines.append("ABB,2025-05-02,1,33.5,33.5")
    lines.append("SBIN#,2025-05-16,50,15.9,795")
    lines.append("INFY#,2025-05-30,10,22,220")
    lines.append("ITC*,2025-06-03,20,6.5,130")

    file_path.write_text("\n".join(lines), encoding="utf-8")


def test_clean_dividend_symbol():
    assert clean_dividend_symbol("INFY#") == "INFY"
    assert clean_dividend_symbol("SBIN#") == "SBIN"
    assert clean_dividend_symbol("ITC*") == "ITC"
    assert clean_dividend_symbol("  tata motors  ") == "TATA MOTORS"
    assert clean_dividend_symbol("") == ""
    assert clean_dividend_symbol(None) == ""


def test_detect_dividend_header_row_csv(tmp_path):
    f0 = tmp_path / "div_0.csv"
    create_sample_dividend_csv(f0, metadata_rows_count=0)
    assert detect_dividend_header_row(f0) == 0

    f5 = tmp_path / "div_5.csv"
    create_sample_dividend_csv(f5, metadata_rows_count=5)
    assert detect_dividend_header_row(f5) == 5


def test_extract_client_id_from_metadata(tmp_path):
    f = tmp_path / "div_meta.csv"
    create_sample_dividend_csv(f, metadata_rows_count=3)
    client_id = extract_client_id_from_metadata(f)
    assert client_id == "FT8594"


def test_parse_sample_csv_and_idempotency(db_conn, tmp_path):
    f = tmp_path / "test_div.csv"
    create_sample_dividend_csv(f, metadata_rows_count=2)

    # 1. First ingestion
    ins1, dups1, tot1 = parse_dividend_file(f, "ZERODHA_DAD", db_conn)
    assert tot1 == 4
    assert ins1 == 4
    assert dups1 == 0

    # Verify cleaned symbols
    rows = db_conn.execute("SELECT symbol, remarks FROM dividends ORDER BY dividend_date ASC;").fetchall()
    symbols = [r[0] for r in rows]
    assert symbols == ["ABB", "SBIN", "INFY", "ITC"]

    # Verify # note preserved in remarks
    infy_row = [r for r in rows if r[0] == "INFY"][0]
    assert "Raw symbol: INFY#" in infy_row[1]

    # 2. Second ingestion (idempotent repeat)
    ins2, dups2, tot2 = parse_dividend_file(f, "ZERODHA_DAD", db_conn)
    assert tot2 == 4
    assert ins2 == 0
    assert dups2 == 4


def test_parse_real_sample_file_if_present(db_conn):
    sample_path = Path("/Users/jigarshah14/Downloads/dividends_2025-04-01_to_2026-03-31.csv")
    if sample_path.is_file():
        ins, dups, total = parse_dividend_file(sample_path, "ZERODHA_SELF", db_conn)
        assert total == 58
        assert ins == 58
        assert dups == 0

        # Repeat to verify deduplication
        ins2, dups2, total2 = parse_dividend_file(sample_path, "ZERODHA_SELF", db_conn)
        assert ins2 == 0
        assert dups2 == 58


def test_fallback_calculations(db_conn, tmp_path):
    # CSV with missing total amount, should auto-calculate from Qty * DPS
    f = tmp_path / "div_fallback.csv"
    f.write_text("Symbol,Date,Shares,DPS\nTCS,2025-08-10,10,12.50\n", encoding="utf-8")

    records, dups, tot = extract_dividend_records(f, "ZERODHA_DAD", db_conn)
    assert len(records) == 1
    # Check amount is 125.0
    assert records[0][6] == 125.0

