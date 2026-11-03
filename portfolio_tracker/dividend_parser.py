"""Zerodha Dividend statement parser with dynamic header detection, symbol cleanup, and idempotent ingestion."""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd

# Synonyms for dividend column matching (normalized tokens: lowercased, underscores)
DIVIDEND_COLUMN_SYNONYMS = {
    "symbol": ["symbol", "tradingsymbol", "stock", "instrument", "scrip"],
    "dividend_date": [
        "ex_date",
        "exdate",
        "record_date",
        "recorddate",
        "date",
        "posting_date",
        "payment_date",
        "credit_date",
        "trade_date",
    ],
    "quantity": ["qty", "quantity", "shares", "shares_held", "volume", "eligible_shares"],
    "dividend_per_share": [
        "dividend_per_share",
        "dividend_rate",
        "rate",
        "dps",
        "rate_per_share",
        "dividend/share",
        "div_per_share",
    ],
    "amount": [
        "total_dividend",
        "total_dividend_amount",
        "gross_dividend",
        "net_dividend",
        "amount",
        "dividend_amount",
        "total_amount",
        "payout",
        "dividend",
        "net_amount",
        "gross_amount",
    ],
    "isin": ["isin", "isin_code", "security_isin"],
    "company_name": ["company_name", "company", "particulars", "name", "security_name"],
    "remarks": ["remarks", "notes", "narration", "description"],
}


def _normalize_token(val: Any) -> str:
    """Normalize string token for comparison."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip().lower()
    return s.replace(" ", "_").replace("-", "_").replace("/", "_")


def clean_dividend_symbol(raw_symbol: Any) -> str:
    """Clean symbol string by stripping whitespace and corporate action markers like '#' or '*'."""
    if raw_symbol is None or pd.isna(raw_symbol):
        return ""
    s = str(raw_symbol).strip().upper()
    # Strip common corporate action flags appended in Zerodha statements
    s = s.rstrip("#*").strip()
    return s


def detect_dividend_header_row(
    file_path: Union[str, Path],
    max_scan_rows: int = 30,
) -> int:
    """Scan the first max_scan_rows of an Excel or CSV file to dynamically locate the table header row.

    Returns:
        0-indexed integer of the detected header row.

    Raises:
        ValueError: If no valid dividend header row is found within max_scan_rows.
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
                for col_name, synonyms in DIVIDEND_COLUMN_SYNONYMS.items():
                    for val in row_vals:
                        if any(syn == val or syn in val for syn in synonyms):
                            matched_groups.add(col_name)
                            break

                # Must have symbol and at least one of amount, dividend_per_share, or dividend_date
                has_symbol = "symbol" in matched_groups
                has_payout = bool({"amount", "dividend_per_share"} & matched_groups)
                if has_symbol and has_payout:
                    return row_idx

    elif suffix in (".xlsx", ".xls"):
        raw_df = pd.read_excel(path, header=None, nrows=max_scan_rows)
        for row_idx in range(len(raw_df)):
            row_vals = [_normalize_token(v) for v in raw_df.iloc[row_idx].dropna()]
            if not row_vals:
                continue

            matched_groups = set()
            for col_name, synonyms in DIVIDEND_COLUMN_SYNONYMS.items():
                for val in row_vals:
                    if any(syn == val or syn in val for syn in synonyms):
                        matched_groups.add(col_name)
                        break

            has_symbol = "symbol" in matched_groups
            has_payout = bool({"amount", "dividend_per_share"} & matched_groups)
            if has_symbol and has_payout:
                return row_idx
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Only .xlsx, .xls, and .csv are supported.")

    raise ValueError(
        f"Could not locate dividend table headers within the first {max_scan_rows} rows of {path.name}."
    )


def extract_client_id_from_metadata(
    file_path: Union[str, Path],
    max_scan_rows: int = 20,
) -> Optional[str]:
    """Scan initial rows for Client ID or Client Code tokens to enable auto-account mapping."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".csv", ".txt"):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                for row_idx, row in enumerate(reader):
                    if row_idx >= max_scan_rows:
                        break
                    row_str = " ".join(row).upper()
                    if "CLIENT ID" in row_str or "CLIENT CODE" in row_str:
                        for idx, cell in enumerate(row):
                            c_upper = str(cell).strip().upper()
                            if ("CLIENT ID" in c_upper or "CLIENT CODE" in c_upper) and idx + 1 < len(row):
                                val = str(row[idx + 1]).strip().upper()
                                if val:
                                    return val
                            elif ":" in c_upper:
                                parts = c_upper.split(":", 1)
                                if "CLIENT" in parts[0] and len(parts) > 1 and parts[1].strip():
                                    return parts[1].strip()
        except Exception:
            pass
    elif suffix in (".xlsx", ".xls"):
        try:
            raw_df = pd.read_excel(path, header=None, nrows=max_scan_rows)
            for row_idx in range(len(raw_df)):
                row = raw_df.iloc[row_idx].dropna().tolist()
                row_str = " ".join(str(x) for x in row).upper()
                if "CLIENT ID" in row_str or "CLIENT CODE" in row_str:
                    for idx, cell in enumerate(row):
                        c_upper = str(cell).strip().upper()
                        if ("CLIENT ID" in c_upper or "CLIENT CODE" in c_upper) and idx + 1 < len(row):
                            val = str(row[idx + 1]).strip().upper()
                            if val:
                                return val
                        elif ":" in c_upper:
                            parts = c_upper.split(":", 1)
                            if "CLIENT" in parts[0] and len(parts) > 1 and parts[1].strip():
                                return parts[1].strip()
        except Exception:
            pass

    return None


def _map_columns(df_columns: List[Any]) -> Dict[str, str]:
    """Map detected dataframe columns to standard internal field names in order of synonym priority."""
    mapping: Dict[str, str] = {}
    normalized_cols = {col: _normalize_token(col) for col in df_columns}

    for standard_name, synonyms in DIVIDEND_COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if standard_name in mapping:
                break
            for orig_col, norm_col in normalized_cols.items():
                if syn == norm_col or (len(syn) > 4 and syn in norm_col):
                    mapping[standard_name] = orig_col
                    break

    return mapping


def generate_fallback_dividend_id(
    account_id: str,
    symbol: str,
    dividend_date: str,
    amount: float,
    quantity: int,
) -> str:
    """Generate a deterministic SHA-256 hash dividend_id for idempotency."""
    raw_payload = f"{account_id}|{symbol}|{dividend_date}|{amount:.4f}|{quantity}"
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:20]
    return f"DIV_HASH_{digest}"


def extract_dividend_records(
    file_path: Union[str, Path],
    account_id: str,
    db_conn: sqlite3.Connection,
    existing_ids: Optional[Set[str]] = None,
) -> Tuple[List[Tuple[Any, ...]], int, int]:
    """Parse a Zerodha Dividend file (CSV or Excel) and extract validated records without committing.

    Args:
        file_path: Path to .xlsx, .xls, or .csv file.
        account_id: Target account identifier (e.g. 'ZERODHA_DAD').
        db_conn: Active SQLite connection for duplicate identification.
        existing_ids: Optional set of known dividend_ids to speed up duplicate detection.

    Returns:
        Tuple of (records_to_insert, duplicate_count, total_valid_rows).
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    # 1. Detect dynamic header row
    header_row = detect_dividend_header_row(path)

    # 2. Read full file starting from detected header
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=header_row)
    else:
        df = pd.read_csv(path, header=header_row)

    col_map = _map_columns(list(df.columns))
    if "symbol" not in col_map:
        raise ValueError(f"Missing required stock symbol column in {path.name}")

    has_date = "dividend_date" in col_map
    has_qty = "quantity" in col_map
    has_dps = "dividend_per_share" in col_map
    has_amt = "amount" in col_map
    has_isin = "isin" in col_map
    has_company = "company_name" in col_map
    has_remarks = "remarks" in col_map

    if not has_amt and not (has_qty and has_dps):
        raise ValueError(
            f"File must provide either total dividend amount or quantity and dividend per share columns."
        )

    # Query existing dividend_ids in the database to calculate duplicates accurately
    if existing_ids is None:
        existing_ids = {
            row[0]
            for row in db_conn.execute("SELECT dividend_id FROM dividends;").fetchall()
        }

    records_to_insert: List[Tuple[Any, ...]] = []
    total_valid_rows = 0

    for _, row in df.iterrows():
        raw_symbol = row[col_map["symbol"]]
        if pd.isna(raw_symbol):
            continue

        clean_sym = clean_dividend_symbol(raw_symbol)
        if not clean_sym:
            continue

        # Parse quantity
        qty = 0
        if has_qty and not pd.isna(row[col_map["quantity"]]):
            try:
                qty = int(round(float(row[col_map["quantity"]])))
                if qty < 0:
                    qty = 0
            except (ValueError, TypeError):
                qty = 0

        # Parse dividend per share
        dps = 0.0
        if has_dps and not pd.isna(row[col_map["dividend_per_share"]]):
            try:
                dps = float(row[col_map["dividend_per_share"]])
                if dps < 0:
                    dps = 0.0
            except (ValueError, TypeError):
                dps = 0.0

        # Parse total dividend amount
        amount = 0.0
        if has_amt and not pd.isna(row[col_map["amount"]]):
            try:
                amount = float(row[col_map["amount"]])
            except (ValueError, TypeError):
                amount = 0.0

        # Fallback calculations if one is missing
        if amount <= 0.0 and qty > 0 and dps > 0.0:
            amount = round(qty * dps, 2)
        elif dps <= 0.0 and qty > 0 and amount > 0.0:
            dps = round(amount / qty, 4)

        if amount <= 0.0 and dps <= 0.0:
            # Skip invalid zero-payout rows
            continue

        # Parse dividend date
        if has_date and not pd.isna(row[col_map["dividend_date"]]):
            try:
                parsed_dt = pd.to_datetime(row[col_map["dividend_date"]])
                date_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

        isin = None
        if has_isin and not pd.isna(row[col_map["isin"]]):
            isin = str(row[col_map["isin"]]).strip()

        remarks = None
        if has_remarks and not pd.isna(row[col_map["remarks"]]):
            remarks = str(row[col_map["remarks"]]).strip()
        elif has_company and not pd.isna(row[col_map["company_name"]]):
            remarks = str(row[col_map["company_name"]]).strip()

        # If raw symbol had special suffixes, note it in remarks if remarks is empty
        raw_sym_str = str(raw_symbol).strip()
        if raw_sym_str != clean_sym and not remarks:
            remarks = f"Raw symbol: {raw_sym_str}"

        dividend_id = generate_fallback_dividend_id(
            account_id=account_id,
            symbol=clean_sym,
            dividend_date=date_str,
            amount=amount,
            quantity=qty,
        )

        total_valid_rows += 1

        if dividend_id not in existing_ids:
            records_to_insert.append((
                dividend_id,
                account_id,
                clean_sym,
                date_str,
                qty,
                dps,
                amount,
                isin,
                remarks,
            ))
            existing_ids.add(dividend_id)

    duplicate_count = total_valid_rows - len(records_to_insert)
    return (records_to_insert, duplicate_count, total_valid_rows)


def parse_dividend_file(
    file_path: Union[str, Path],
    account_id: str,
    db_conn: sqlite3.Connection,
) -> Tuple[int, int, int]:
    """Parse a Zerodha Dividend file and idempotently ingest transactions into the database.

    Returns:
        Tuple of (inserted_count, duplicate_count, total_count).
    """
    from portfolio_tracker.db import commit_dividend_records

    records_to_insert, duplicate_count, total_valid_rows = extract_dividend_records(
        file_path=file_path,
        account_id=account_id,
        db_conn=db_conn,
    )
    inserted_count = commit_dividend_records(records_to_insert, db_conn)
    return (inserted_count, duplicate_count, total_valid_rows)

