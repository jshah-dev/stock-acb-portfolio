"""Unit tests for stock symbol renaming, corporate actions mapping, and cost basis unification."""

import pytest
from PySide6.QtWidgets import QApplication

from portfolio_tracker.db import (
    add_symbol_mapping,
    delete_symbol_mapping,
    get_all_symbols,
    get_symbol_mappings,
    init_db,
    insert_manual_transaction,
)
from portfolio_tracker.engine import get_holdings, get_portfolio_summary
from portfolio_tracker.ui.symbol_mapping_dialog import SymbolMappingDialog


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "mapping_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_symbol_mapping_db_crud(db_conn):
    """Test inserting, reading, updating, and deleting symbol mappings."""
    # 1. Validation checks
    with pytest.raises(ValueError, match="Source.*cannot be empty"):
        add_symbol_mapping(db_conn, "", "ZYDUSLIFE")

    with pytest.raises(ValueError, match="Target.*cannot be empty"):
        add_symbol_mapping(db_conn, "CADILAHC", "")

    with pytest.raises(ValueError, match="identical"):
        add_symbol_mapping(db_conn, "TCS", "TCS")

    # 2. Add mapping
    res = add_symbol_mapping(db_conn, "CADILAHC", "ZYDUSLIFE", "Renamed in 2022")
    assert res["source_symbol"] == "CADILAHC"
    assert res["target_symbol"] == "ZYDUSLIFE"

    # 3. List mappings
    mappings = get_symbol_mappings(db_conn)
    assert len(mappings) == 1
    assert mappings[0]["source_symbol"] == "CADILAHC"
    assert mappings[0]["target_symbol"] == "ZYDUSLIFE"
    assert mappings[0]["notes"] == "Renamed in 2022"

    # 4. Check autocomplete index contains both
    symbols = get_all_symbols(db_conn)
    assert "CADILAHC" in symbols
    assert "ZYDUSLIFE" in symbols

    # 5. Delete mapping
    deleted = delete_symbol_mapping(db_conn, "CADILAHC")
    assert deleted is True
    assert len(get_symbol_mappings(db_conn)) == 0


def test_corporate_action_anomaly_healed_by_symbol_mapping(db_conn):
    """Test scenario where buy was under CADILAHC and sell was under ZYDUSLIFE:
    Without mapping: ZYDUSLIFE throws false anomaly 'Sell > Buy'.
    With mapping: CADILAHC and ZYDUSLIFE unify under ZYDUSLIFE with clean closed position.
    """
    # Buy 100 shares of CADILAHC in 2021
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "CADILAHC", "BUY", 100, 400.0, "2021-05-10 10:00:00")
    # Sell 100 shares of ZYDUSLIFE in 2023
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "ZYDUSLIFE", "SELL", 100, 600.0, "2023-08-15 11:00:00")

    # 1. Without mapping:
    df_raw = get_holdings(db_conn, include_closed=True)
    assert len(df_raw) == 2
    zydus_raw = df_raw[df_raw["symbol"] == "ZYDUSLIFE"].iloc[0]
    assert bool(zydus_raw["is_anomalous"]) is True
    assert "Sell > Buy" in zydus_raw["status"]

    # 2. Apply symbol mapping
    add_symbol_mapping(db_conn, "CADILAHC", "ZYDUSLIFE", "Rebranding corporate action")

    # 3. With mapping: CADILAHC is aliased to ZYDUSLIFE
    df_mapped = get_holdings(db_conn, include_closed=True)
    assert len(df_mapped) == 1
    row = df_mapped.iloc[0]

    assert row["symbol"] == "ZYDUSLIFE"
    assert row["net_qty"] == 0
    assert bool(row["is_closed"]) is True
    assert bool(row["is_anomalous"]) is False
    assert row["total_buy_cost"] == 40000.0
    assert row["total_proceeds"] == 60000.0
    assert row["booked_pnl"] == 20000.0
    assert "CADILAHC" in row["mapped_sources"]


def test_corporate_action_partial_sale_acb_identity(db_conn):
    """Test 9-column ACB math when a renamed stock is partially sold:
    Buy 100 CADILAHC @ ₹400 = ₹40,000
    Sell 50 ZYDUSLIFE @ ₹600 = ₹30,000
    Shares Held = 50
    Actual Exposure = 50 * ₹400 = ₹20,000
    Booked P&L = ₹30,000 - (50 * ₹400) = ₹10,000
    Net Exposure = ₹20,000 - ₹10,000 = ₹10,000 (Identity holds!)
    Effective Avg Price = ₹10,000 / 50 = ₹200.00
    """
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "CADILAHC", "BUY", 100, 400.0, "2021-05-10 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "ZYDUSLIFE", "SELL", 50, 600.0, "2023-08-15 11:00:00")

    add_symbol_mapping(db_conn, "CADILAHC", "ZYDUSLIFE")

    df = get_holdings(db_conn)
    assert len(df) == 1
    row = df.iloc[0]

    assert row["symbol"] == "ZYDUSLIFE"
    assert row["net_qty"] == 50
    assert row["avg_buy_price"] == 400.0
    assert row["total_buy_cost"] == 40000.0
    assert row["total_proceeds"] == 30000.0
    assert row["actual_exposure"] == 20000.0
    assert row["booked_pnl"] == 10000.0
    assert row["net_exposure"] == 10000.0
    assert row["effective_avg"] == 200.0
    # Core mathematical proof:
    assert row["actual_exposure"] - row["booked_pnl"] == row["net_exposure"]

    summary = get_portfolio_summary(df)
    assert summary["total_net_exposure"] == 10000.0
    assert summary["total_actual_exposure"] == 20000.0
    assert summary["total_booked_profit"] == 10000.0


def test_symbol_mapping_dialog_ui(monkeypatch, qapp, db_conn):
    """Verify SymbolMappingDialog UI interactions offscreen."""
    from PySide6.QtWidgets import QMessageBox

    # Auto-confirm any delete prompt
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    insert_manual_transaction(db_conn, "ZERODHA_SELF", "MOTHERSUMI", "BUY", 100, 150.0, "2021-01-01")

    dlg = SymbolMappingDialog(db_conn)
    assert dlg.table.columnCount() == 5
    assert dlg.table.rowCount() == 0

    # Fill form
    dlg.combo_source.setEditText("MOTHERSUMI")
    dlg.combo_target.setEditText("MOTHERSON")
    dlg.txt_notes.setText("Demerger & Renaming")

    # Add mapping
    dlg._add_mapping()
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 0).text() == "MOTHERSUMI"
    assert dlg.table.item(0, 1).text() == "MOTHERSON"
    assert "Successfully mapped" in dlg.lbl_form_status.text()

    # Delete mapping
    dlg._delete_mapping("MOTHERSUMI")
    assert dlg.table.rowCount() == 0
    dlg.close()
