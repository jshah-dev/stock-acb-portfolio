"""Zerodha Tradebook parser with dynamic header detection, column normalization, and idempotent deduplication."""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd

# Synonyms for column matching (lowercased and underscores)
COLUMN_SYNONYMS = {
    "symbol": ["tradingsymbol", "symbol", "stock", "instrument", "scrip"],
    "trade_date": ["order_execution_time", "trade_date", "date", "execution_date", "trade_time"],
    "transaction_type": ["trade_type", "type", "transaction_type", "side", "buy/sell"],
    "quantity": ["quantity", "qty", "volume", "shares"],
    "price": ["price", "trade_price", "rate", "avg_price", "execution_price"],
    "trade_id": ["trade_id", "trade id", "trade_no", "order_id", "id"],
}


def _normalize_token(val: Any) -> str:
    """Normalize string token for comparison."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip().lower()
    return s.replace(" ", "_").replace("-", "_")


def detect_header_row(
    file_path: Union[str, Path],
    max_scan_rows: int = 25,
) -> int:
    """Scan the first max_scan_rows of an Excel or CSV file to dynamically locate the table header row.

    Returns:
        0-indexed integer of the detected header row.

    Raises:
        ValueError: If no valid tradebook header row is found within max_scan_rows.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".csv", ".txt"):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                if row_idx >= max_scan_rows:
                    break
                row_vals = [_normalize_token(v) for v in row if v]
                if not row_vals:
                    continue

                matched_groups: Set[str] = set()
                for col_name, synonyms in COLUMN_SYNONYMS.items():
                    for val in row_vals:
                        if any(syn == val or syn in val for syn in synonyms):
                            matched_groups.add(col_name)
                            break

                essential = {"symbol", "transaction_type", "quantity", "price"}
                if essential.issubset(matched_groups):
                    return row_idx

    elif suffix in (".xlsx", ".xls"):
        raw_df = pd.read_excel(path, header=None, nrows=max_scan_rows)
        for row_idx in range(len(raw_df)):
            row_vals = [_normalize_token(v) for v in raw_df.iloc[row_idx].dropna()]
            if not row_vals:
                continue

            matched_groups = set()
            for col_name, synonyms in COLUMN_SYNONYMS.items():
                for val in row_vals:
                    if any(syn == val or syn in val for syn in synonyms):
                        matched_groups.add(col_name)
                        break

            essential = {"symbol", "transaction_type", "quantity", "price"}
            if essential.issubset(matched_groups):
                return row_idx
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Only .xlsx, .xls, and .csv are supported.")

    raise ValueError(
        f"Could not locate tradebook table headers within the first {max_scan_rows} rows of {path.name}."
    )


def _map_columns(df_columns: List[Any]) -> Dict[str, str]:
    """Map detected dataframe columns to standard internal field names in order of synonym priority."""
    mapping: Dict[str, str] = {}
    normalized_cols = {col: _normalize_token(col) for col in df_columns}

    for standard_name, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if standard_name in mapping:
                break
            for orig_col, norm_col in normalized_cols.items():
                if syn == norm_col or (len(syn) > 4 and syn in norm_col):
                    mapping[standard_name] = orig_col
                    break

    return mapping


def generate_fallback_trade_id(
    account_id: str,
    symbol: str,
    trade_date: str,
    quantity: int,
    price: float,
    transaction_type: str,
) -> str:
    """Generate a deterministic SHA-256 hash trade_id for files lacking broker execution IDs."""
    raw_payload = f"{account_id}|{symbol}|{trade_date}|{quantity}|{price:.4f}|{transaction_type}"
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:20]
    return f"HASH_{digest}"


def extract_tradebook_records(
    file_path: Union[str, Path],
    account_id: str,
    db_conn: sqlite3.Connection,
    existing_ids: Optional[Set[str]] = None,
) -> Tuple[List[Tuple[Any, ...]], int, int]:
    """Parse a Zerodha Tradebook file (CSV or Excel) and extract validated records without committing.

    Args:
        file_path: Path to .xlsx, .xls, or .csv file.
        account_id: Target account identifier (e.g. 'ZERODHA_DAD').
        db_conn: Active SQLite connection for duplicate identification.

    Returns:
        Tuple of (records_to_insert, duplicate_count, total_count).

    Raises:
        ValueError: On parsing errors or missing essential columns.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    # 1. Detect dynamic header row
    header_row = detect_header_row(path)

    # 2. Read full file starting from detected header
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=header_row)
    else:
        df = pd.read_csv(path, header=header_row)

    col_map = _map_columns(list(df.columns))
    required = ["symbol", "transaction_type", "quantity", "price"]
    for req in required:
        if req not in col_map:
            raise ValueError(f"Missing required tradebook column: '{req}'")

    has_date = "trade_date" in col_map
    has_trade_id = "trade_id" in col_map

    # Query existing trade_ids in the database to accurately calculate duplicates
    if existing_ids is None:
        existing_ids = {
            row[0]
            for row in db_conn.execute("SELECT trade_id FROM transactions;").fetchall()
        }

    records_to_insert: List[Tuple[Any, ...]] = []
    total_valid_rows = 0

    for _, row in df.iterrows():
        raw_symbol = row[col_map["symbol"]]
        raw_type = row[col_map["transaction_type"]]
        raw_qty = row[col_map["quantity"]]
        raw_price = row[col_map["price"]]

        # Skip empty or summary rows
        if pd.isna(raw_symbol) or pd.isna(raw_qty) or pd.isna(raw_price):
            continue

        symbol_str = str(raw_symbol).strip().upper()
        if not symbol_str:
            continue

        # Parse and normalize transaction type
        type_str = str(raw_type).strip().upper()
        if type_str in ("BUY", "B") or type_str.startswith("BUY"):
            norm_type = "BUY"
        elif type_str in ("SELL", "S") or type_str.startswith("SELL"):
            norm_type = "SELL"
        else:
            # Skip non-trade entries (e.g. dividends or corporate action summaries without buy/sell)
            continue

        # Parse quantity and price (price >= 0 supported for bonus shares)
        try:
            qty = int(round(float(raw_qty)))
            price = float(raw_price)
            if qty <= 0 or price < 0:
                continue
        except (ValueError, TypeError):
            continue

        # Parse trade date
        if has_date and not pd.isna(row[col_map["trade_date"]]):
            try:
                parsed_dt = pd.to_datetime(row[col_map["trade_date"]])
                date_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine trade ID
        if has_trade_id and not pd.isna(row[col_map["trade_id"]]):
            raw_tid = str(row[col_map["trade_id"]]).strip()
            # If trade_id is float like 12345.0, convert to integer string
            if raw_tid.endswith(".0"):
                raw_tid = raw_tid[:-2]
            trade_id = raw_tid if raw_tid else generate_fallback_trade_id(
                account_id, symbol_str, date_str, qty, price, norm_type
            )
        else:
            trade_id = generate_fallback_trade_id(
                account_id, symbol_str, date_str, qty, price, norm_type
            )

        total_valid_rows += 1

        if trade_id not in existing_ids:
            records_to_insert.append((
                trade_id,
                account_id,
                symbol_str,
                norm_type,
                qty,
                price,
                date_str,
                None,  # notes
            ))
            existing_ids.add(trade_id)

    duplicate_count = total_valid_rows - len(records_to_insert)
    return (records_to_insert, duplicate_count, total_valid_rows)


def commit_tradebook_records(
    records_to_insert: List[Tuple[Any, ...]],
    db_conn: sqlite3.Connection,
) -> int:
    """Commit extracted tradebook records to SQLite in a batch transaction."""
    if not records_to_insert:
        return 0

    with db_conn:
        db_conn.executemany(
            """
            INSERT OR IGNORE INTO transactions 
            (trade_id, account_id, symbol, transaction_type, quantity, price, trade_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            records_to_insert,
        )

        # Record unique symbols in dedicated symbols table for recommendation engine
        unique_syms = list({(r[2],) for r in records_to_insert if r[2]})
        if unique_syms:
            db_conn.executemany(
                """
                INSERT INTO symbols (symbol, last_used) VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET last_used = CURRENT_TIMESTAMP;
                """,
                unique_syms,
            )

    return len(records_to_insert)


def parse_tradebook(
    file_path: Union[str, Path],
    account_id: str,
    db_conn: sqlite3.Connection,
) -> Tuple[int, int, int]:
    """Parse a Zerodha Tradebook file (CSV or Excel) and idempotently ingest transactions into the database.

    Args:
        file_path: Path to .xlsx, .xls, or .csv file.
        account_id: Target account identifier (e.g. 'ZERODHA_DAD').
        db_conn: Active SQLite connection.

    Returns:
        Tuple of (inserted_count, duplicate_count, total_count).

    Raises:
        ValueError: On parsing errors or missing essential columns.
    """
    records_to_insert, duplicate_count, total_valid_rows = extract_tradebook_records(
        file_path=file_path,
        account_id=account_id,
        db_conn=db_conn,
    )
    inserted_count = commit_tradebook_records(records_to_insert, db_conn)
    return (inserted_count, duplicate_count, total_valid_rows)
