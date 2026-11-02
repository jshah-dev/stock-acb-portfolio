"""Database storage engine, schema migrations, account lifecycle, and backup utilities."""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from portfolio_tracker.config import get_active_db_path


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Create and return a configured SQLite connection with WAL mode and foreign keys enabled."""
    path = Path(db_path) if db_path else get_active_db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        pass

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Enforce safe concurrency and relational integrity
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA temp_store = MEMORY;")

    return conn


def init_db(db_path_or_conn: Optional[Union[str, Path, sqlite3.Connection]] = None) -> sqlite3.Connection:
    """Initialize schema, create indexes, and seed default starter accounts if empty."""
    if isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = get_connection(db_path_or_conn)
    with conn:
        # 1. Accounts Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL,
                broker TEXT NOT NULL DEFAULT 'Zerodha',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Transactions Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                trade_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                price REAL NOT NULL CHECK(price >= 0),
                trade_date TIMESTAMP NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
            );
        """)

        # Migration: Relax old CHECK(price > 0) to CHECK(price >= 0) to support bonus shares (price = 0)
        table_sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions';"
        ).fetchone()
        if table_sql_row and "price > 0" in table_sql_row[0]:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("""
                CREATE TABLE transactions_migrated (
                    trade_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    price REAL NOT NULL CHECK(price >= 0),
                    trade_date TIMESTAMP NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );
            """)
            conn.execute("INSERT INTO transactions_migrated SELECT * FROM transactions;")
            conn.execute("DROP TABLE transactions;")
            conn.execute("ALTER TABLE transactions_migrated RENAME TO transactions;")
            conn.execute("PRAGMA foreign_keys = ON;")

        # 3. Query Optimization Indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_account_symbol_date 
            ON transactions(account_id, symbol, trade_date);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_symbol_date 
            ON transactions(symbol, trade_date);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_account 
            ON transactions(account_id);
        """)

        # 4. Dedicated Stock Symbols Table (for search & autocomplete recommendations)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_name 
            ON symbols(symbol);
        """)

        # 5. Symbol Name Change / Corporate Action Mappings Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS symbol_mappings (
                source_symbol TEXT PRIMARY KEY,
                target_symbol TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_mappings_target 
            ON symbol_mappings(target_symbol);
        """)

        # Backfill symbols from transactions table if any exist
        conn.execute("""
            INSERT OR IGNORE INTO symbols (symbol)
            SELECT DISTINCT UPPER(TRIM(symbol)) FROM transactions 
            WHERE symbol IS NOT NULL AND TRIM(symbol) != '';
        """)

        # 5. Initial Starter Seeding
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM accounts;")
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute("""
                INSERT INTO accounts (account_id, user_name, broker) VALUES 
                ('ZERODHA_DAD', "Father's Zerodha", 'Zerodha'),
                ('ZERODHA_SELF', "Self Zerodha", 'Zerodha');
            """)

    return conn


# --- Account Lifecycle Management ---

def get_accounts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all accounts ordered by creation, including their total transaction count."""
    query = """
        SELECT a.account_id, a.user_name, a.broker, a.created_at,
               COUNT(t.trade_id) AS transaction_count
        FROM accounts a
        LEFT JOIN transactions t ON a.account_id = t.account_id
        GROUP BY a.account_id, a.user_name, a.broker, a.created_at
        ORDER BY a.created_at ASC;
    """
    rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def get_account_transaction_count(conn: sqlite3.Connection, account_id: str) -> int:
    """Return the number of transactions associated with an account."""
    row = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = ?;", (account_id,)
    ).fetchone()
    return row[0] if row else 0


def add_account(
    conn: sqlite3.Connection,
    account_id: str,
    user_name: str,
    broker: str = "Zerodha",
) -> Dict[str, Any]:
    """Add a new family account."""
    acc_id = account_id.strip().upper()
    name = user_name.strip()
    brk = broker.strip() or "Zerodha"

    if not acc_id:
        raise ValueError("Account ID cannot be empty.")
    if not name:
        raise ValueError("Account user name cannot be empty.")

    with conn:
        conn.execute(
            "INSERT INTO accounts (account_id, user_name, broker) VALUES (?, ?, ?);",
            (acc_id, name, brk),
        )

    return {"account_id": acc_id, "user_name": name, "broker": brk}


def update_account(
    conn: sqlite3.Connection,
    old_account_id: str,
    new_account_id: str,
    new_user_name: str,
    new_broker: str = "Zerodha",
) -> None:
    """Update an account's ID and display name / description.
    
    If account_id changes, cascades the change to all referencing transactions.
    """
    old_id = old_account_id.strip().upper()
    new_id = new_account_id.strip().upper()
    name = new_user_name.strip()
    broker = new_broker.strip() or "Zerodha"

    if not old_id:
        raise ValueError("Old Account ID cannot be empty.")
    if not new_id:
        raise ValueError("New Account ID cannot be empty.")
    if not name:
        raise ValueError("Display Name / Description cannot be empty.")

    with conn:
        old_row = conn.execute(
            "SELECT account_id FROM accounts WHERE UPPER(TRIM(account_id)) = ?;", (old_id,)
        ).fetchone()
        if not old_row:
            raise ValueError(f"Account '{old_id}' does not exist.")

        if old_id != new_id:
            clash = conn.execute(
                "SELECT account_id FROM accounts WHERE UPPER(TRIM(account_id)) = ?;", (new_id,)
            ).fetchone()
            if clash:
                raise ValueError(f"Account ID '{new_id}' is already in use.")

            # Atomic migration of account and child transactions
            conn.execute(
                "INSERT INTO accounts (account_id, user_name, broker) VALUES (?, ?, ?);",
                (new_id, name, broker),
            )
            conn.execute(
                "UPDATE transactions SET account_id = ? WHERE UPPER(TRIM(account_id)) = ?;",
                (new_id, old_id),
            )
            conn.execute(
                "DELETE FROM accounts WHERE UPPER(TRIM(account_id)) = ?;",
                (old_id,),
            )
        else:
            conn.execute(
                "UPDATE accounts SET user_name = ?, broker = ? WHERE UPPER(TRIM(account_id)) = ?;",
                (name, broker, old_id),
            )


def delete_account(conn: sqlite3.Connection, account_id: str) -> int:
    """Delete an account and cascade delete all its transactions.

    Raises:
        ValueError: If attempting to delete the last remaining account or non-existent account.

    Returns:
        The number of cascaded transactions that were deleted.
    """
    # Guard: Do not allow deleting the last remaining account
    total_accounts = conn.execute("SELECT COUNT(*) FROM accounts;").fetchone()[0]
    if total_accounts <= 1:
        raise ValueError("Cannot delete the only remaining account in the portfolio.")

    tx_count = get_account_transaction_count(conn, account_id)

    with conn:
        cursor = conn.execute("DELETE FROM accounts WHERE account_id = ?;", (account_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Account '{account_id}' does not exist.")

    return tx_count


# --- Manual Transactions & Single Trade Audit ---

def insert_manual_transaction(
    conn: sqlite3.Connection,
    account_id: str,
    symbol: str,
    transaction_type: str,
    quantity: int,
    price: float,
    trade_date: Union[str, datetime],
    notes: Optional[str] = None,
) -> str:
    """Insert a manual transaction (e.g. to fix missing records or corporate actions).

    Returns:
        Generated unique trade_id.
    """
    acc_id = account_id.strip()
    sym = symbol.strip().upper()
    tx_type = transaction_type.strip().upper()

    if tx_type not in ("BUY", "SELL"):
        raise ValueError("Transaction type must be 'BUY' or 'SELL'.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")
    if price < 0:
        raise ValueError("Price cannot be negative.")
    if not sym:
        raise ValueError("Symbol cannot be empty.")

    # Format date to ISO string
    if isinstance(trade_date, datetime):
        date_str = trade_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_str = str(trade_date).strip()

    ts_slug = datetime.now().strftime("%Y%m%d%H%M%S")
    rand_slug = uuid.uuid4().hex[:8]
    trade_id = f"MANUAL_{acc_id}_{ts_slug}_{rand_slug}"

    with conn:
        conn.execute(
            """
            INSERT INTO transactions 
            (trade_id, account_id, symbol, transaction_type, quantity, price, trade_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (trade_id, acc_id, sym, tx_type, quantity, price, date_str, notes),
        )
        conn.execute(
            """
            INSERT INTO symbols (symbol, last_used) VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET last_used = CURRENT_TIMESTAMP;
            """,
            (sym,),
        )

    return trade_id


def record_symbol(conn: sqlite3.Connection, symbol: str) -> None:
    """Store or touch a stock symbol in the dedicated symbols table."""
    clean_sym = symbol.strip().upper()
    if clean_sym:
        with conn:
            conn.execute(
                """
                INSERT INTO symbols (symbol, last_used) VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET last_used = CURRENT_TIMESTAMP;
                """,
                (clean_sym,),
            )


def get_all_symbols(conn: sqlite3.Connection) -> List[str]:
    """Return a sorted list of all unique stock symbols in the system for autocomplete recommendations."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol FROM symbols 
        UNION 
        SELECT DISTINCT UPPER(TRIM(symbol)) FROM transactions 
        WHERE symbol IS NOT NULL AND TRIM(symbol) != ''
        UNION
        SELECT source_symbol FROM symbol_mappings
        UNION
        SELECT target_symbol FROM symbol_mappings
        ORDER BY symbol ASC;
    """)
    return [row[0] for row in cursor.fetchall() if row[0]]


# --- Symbol Name Change / Corporate Actions Mapping ---

def add_symbol_mapping(
    conn: sqlite3.Connection,
    source_symbol: str,
    target_symbol: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Add or update a symbol mapping to translate older/renamed tickers to canonical tickers.

    Example:
        source_symbol: 'CADILAHC', target_symbol: 'ZYDUSLIFE'
    """
    src = source_symbol.strip().upper()
    tgt = target_symbol.strip().upper()
    clean_notes = notes.strip() if notes else None

    if not src:
        raise ValueError("Source (original) symbol cannot be empty.")
    if not tgt:
        raise ValueError("Target (canonical) symbol cannot be empty.")
    if src == tgt:
        raise ValueError("Source symbol and Target symbol cannot be identical.")

    with conn:
        conn.execute(
            """
            INSERT INTO symbol_mappings (source_symbol, target_symbol, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(source_symbol) DO UPDATE SET 
                target_symbol = excluded.target_symbol,
                notes = excluded.notes,
                created_at = CURRENT_TIMESTAMP;
            """,
            (src, tgt, clean_notes),
        )
        # Record both symbols in autocomplete index
        record_symbol(conn, src)
        record_symbol(conn, tgt)

    return {"source_symbol": src, "target_symbol": tgt, "notes": clean_notes}


def delete_symbol_mapping(conn: sqlite3.Connection, source_symbol: str) -> bool:
    """Remove a symbol mapping by source symbol."""
    src = source_symbol.strip().upper()
    with conn:
        cursor = conn.execute("DELETE FROM symbol_mappings WHERE UPPER(TRIM(source_symbol)) = ?;", (src,))
        return cursor.rowcount > 0


def get_symbol_mappings(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all configured symbol mappings along with the count of affected historical trades."""
    query = """
        SELECT m.source_symbol, m.target_symbol, m.notes, m.created_at,
               (SELECT COUNT(*) FROM transactions t WHERE UPPER(TRIM(t.symbol)) = UPPER(TRIM(m.source_symbol))) AS trade_count
        FROM symbol_mappings m
        ORDER BY m.source_symbol ASC;
    """
    rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def get_symbol_trade_count(conn: sqlite3.Connection, symbol: str) -> int:
    """Return number of transactions matching a given stock symbol."""
    sym = symbol.strip().upper()
    row = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE UPPER(TRIM(symbol)) = ?;", (sym,)
    ).fetchone()
    return row[0] if row else 0



def get_transaction(conn: sqlite3.Connection, trade_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single transaction with account metadata by trade_id."""
    query = """
        SELECT t.trade_id, t.account_id, a.user_name, t.symbol, 
               t.transaction_type, t.quantity, t.price, t.trade_date, 
               t.notes, t.created_at
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        WHERE t.trade_id = ?;
    """
    row = conn.execute(query, (trade_id,)).fetchone()
    return dict(row) if row else None


def update_transaction(
    conn: sqlite3.Connection,
    trade_id: str,
    account_id: str,
    symbol: str,
    transaction_type: str,
    quantity: int,
    price: float,
    trade_date: Union[str, datetime],
    notes: Optional[str] = None,
) -> bool:
    """Update an existing transaction (e.g. for stock split, bonus, or trade corrections)."""
    acc_id = account_id.strip()
    sym = symbol.strip().upper()
    tx_type = transaction_type.strip().upper()

    if tx_type not in ("BUY", "SELL"):
        raise ValueError("Transaction type must be 'BUY' or 'SELL'.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")
    if price < 0:
        raise ValueError("Price cannot be negative.")
    if not sym:
        raise ValueError("Symbol cannot be empty.")

    if isinstance(trade_date, datetime):
        date_str = trade_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_str = str(trade_date).strip()

    with conn:
        cursor = conn.execute(
            """
            UPDATE transactions 
            SET account_id = ?, symbol = ?, transaction_type = ?, quantity = ?, price = ?, trade_date = ?, notes = ?
            WHERE trade_id = ?;
            """,
            (acc_id, sym, tx_type, quantity, price, date_str, notes, trade_id),
        )
        if cursor.rowcount > 0:
            conn.execute(
                """
                INSERT INTO symbols (symbol, last_used) VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET last_used = CURRENT_TIMESTAMP;
                """,
                (sym,),
            )
            return True
        return False


def delete_transaction(conn: sqlite3.Connection, trade_id: str) -> bool:
    """Delete a single transaction by trade_id."""
    with conn:
        cursor = conn.execute("DELETE FROM transactions WHERE trade_id = ?;", (trade_id,))
        return cursor.rowcount > 0


def get_recent_transactions(
    conn: sqlite3.Connection,
    account_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieve transactions with account metadata for audit and review.
    
    Args:
        conn: SQLite connection.
        account_id: Optional account filter.
        limit: Optional maximum rows to return. If None or <= 0, returns all transactions.
    """
    query = """
        SELECT t.trade_id, t.account_id, a.user_name, t.symbol, 
               t.transaction_type, t.quantity, t.price, t.trade_date, 
               t.notes, t.created_at
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
    """
    params: List[Any] = []
    if account_id:
        query += " WHERE t.account_id = ?"
        params.append(account_id)

    query += " ORDER BY t.trade_date DESC, t.created_at DESC"
    if limit is not None and limit > 0:
        query += " LIMIT ?;"
        params.append(limit)
    else:
        query += ";"

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_all_transactions(
    conn: sqlite3.Connection,
    account_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all historical transactions with account metadata without truncation."""
    return get_recent_transactions(conn, account_id=account_id, limit=None)


# --- Database Backup and Restore Utilities ---

def backup_database(
    conn: sqlite3.Connection,
    dest_path: Union[str, Path],
) -> Path:
    """Create an atomic live backup snapshot of the SQLite database."""
    target = Path(dest_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    dest_conn = sqlite3.connect(str(target))
    try:
        with dest_conn:
            conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()

    return target


def restore_database(
    source_backup_path: Union[str, Path],
    target_db_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Restore database from a backup file."""
    src = Path(source_backup_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source backup file not found: {src}")

    target = Path(target_db_path) if target_db_path else get_active_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Use native backup to restore cleanly
    src_conn = sqlite3.connect(str(src))
    dest_conn = sqlite3.connect(str(target))
    try:
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
    finally:
        src_conn.close()
        dest_conn.close()

    return target

