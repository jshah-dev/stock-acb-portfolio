"""Offscreen GUI tests for PySide6 MainWindow, HoldingsView, and Dialogs."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication

from portfolio_tracker.db import init_db, insert_manual_transaction
from portfolio_tracker.ui.account_manager_dialog import AccountManagerDialog
from portfolio_tracker.ui.edit_trade_dialog import EditTradeDialog
from portfolio_tracker.ui.main_window import MainWindow
from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
from portfolio_tracker.ui.transaction_history_dialog import TransactionHistoryDialog
from portfolio_tracker.ui.upload_view import UploadView


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "ui_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_main_window_tabs_and_structure(qapp, db_conn):
    """Verify MainWindow initializes with both tabs and correct branding."""
    win = MainWindow(db_conn)
    assert win.tabs.count() == 2
    assert "Holdings" in win.tabs.tabText(0)
    assert "Import" in win.tabs.tabText(1)
    assert win.windowTitle() == "Stock ACB Portfolio Tracker"

    # Check HoldingsView initialized
    hv = win.holdings_view
    assert hv.combo_account.count() >= 3  # Consolidated + 2 default accounts

    # Check Top Bar merged DB Settings and Close button
    assert hasattr(win, "btn_db_settings")
    assert hasattr(win, "btn_close")
    assert "Database:" in win.btn_db_settings.text()
    assert win.btn_close.property("class") == "danger-btn"

    # Check Symbol Mapping button
    assert hasattr(hv, "btn_symbol_mapping")
    assert hv.btn_symbol_mapping.text() == "Symbol Mapping"

    win.close()


def test_holdings_view_table_and_kpis(qapp, db_conn):
    """Verify HoldingsView updates 9-column table rows, ACB tooltips, and KPI cards."""
    # Seed 1 active stock and 1 risk-free stock
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "TCS", "BUY", 100, 3000.0, "2026-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "TCS", "SELL", 40, 3500.0, "2026-01-10")  # Cost 300k, Proc 140k -> Net Exp: 160k, Actual: 180k, Booked: 20k

    # Risk free stock
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 100, 1000.0, "2026-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "SELL", 90, 1500.0, "2026-01-10")  # Cost 100k, Proc 135k -> Net Exp: 0, Booked: 45k

    win = MainWindow(db_conn)
    hv = win.holdings_view
    hv.refresh_data()

    # Verify KPI values
    assert "160,000.00" in hv.card_risk.value_label.text()
    assert "2 Stocks" in hv.card_stocks.value_label.text()
    assert "1 risk-free positions" in hv.card_stocks.sub_label.text()

    # Verify Table rows and 9 columns
    assert hv.table.rowCount() == 2
    assert hv.table.columnCount() == 9
    symbols = [hv.table.item(r, 0).text() for r in range(hv.table.rowCount())]
    assert "TCS" in symbols
    assert "INFY" in symbols

    # Check house money tooltip on INFY (Col 7: Effective Avg Price)
    infy_row = symbols.index("INFY")
    infy_avg_item = hv.table.item(infy_row, 7)
    assert "Risk Free" in infy_avg_item.text()
    assert "Pure House Money" in infy_avg_item.toolTip()
    assert "Cash Extracted" in infy_avg_item.toolTip()

    # Check INFY Col 5 Booked P&L and Col 6 Net Exposure
    infy_pnl_item = hv.table.item(infy_row, 5)
    assert "(+) ₹45,000.00" in infy_pnl_item.text()
    assert infy_pnl_item.foreground().color().name().upper() == "#047857"
    assert infy_pnl_item.background().color().name().upper() == "#DCFCE7"

    infy_net_item = hv.table.item(infy_row, 6)
    assert "Risk Free" in infy_net_item.text()
    assert infy_net_item.foreground().color().name().upper() == "#047857"
    assert infy_net_item.background().color().name().upper() == "#DCFCE7"

    # Check TCS: Actual Exposure (Col 4), Booked P&L (Col 5), Net Exposure (Col 6)
    tcs_row = symbols.index("TCS")
    tcs_act_item = hv.table.item(tcs_row, 4)
    assert "₹180,000.00" in tcs_act_item.text()

    tcs_pnl_item = hv.table.item(tcs_row, 5)
    assert "(+) ₹20,000.00" in tcs_pnl_item.text()
    assert tcs_pnl_item.foreground().color().name().upper() == "#047857"

    tcs_net_item = hv.table.item(tcs_row, 6)
    assert "₹160,000.00" in tcs_net_item.text()

    # Verify buttons are labeled and not empty
    assert hv.btn_manual_trade.text() == "+ Add Trade"
    assert hv.btn_export.text() == "Export Excel"

    # Verify closed positions show ₹0.00 (not nan) in effective average price
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "WIPRO", "BUY", 50, 400.0, "2026-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "WIPRO", "SELL", 50, 450.0, "2026-01-15")
    hv.chk_closed.setChecked(True)
    hv.refresh_data()
    wipro_symbols = [hv.table.item(r, 0).text() for r in range(hv.table.rowCount())]
    assert "WIPRO" in wipro_symbols
    wipro_row = wipro_symbols.index("WIPRO")
    wipro_avg_item = hv.table.item(wipro_row, 7)
    assert wipro_avg_item.text() == "₹0.00"
    assert "nan" not in wipro_avg_item.text().lower()

    # Verify table is strictly read-only
    from PySide6.QtWidgets import QAbstractItemView
    assert hv.table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert not (hv.table.item(0, 0).flags() & Qt.ItemIsEditable)

    # Verify Native Chart & Controls Bar UI components
    from PySide6.QtWidgets import QScrollArea
    from portfolio_tracker.ui.charts import NativeChartView
    assert isinstance(hv.scroll_area, QScrollArea)
    assert isinstance(hv.chart_view, NativeChartView)
    assert hv.chart_view.chart.series() is not None
    assert hv.date_cutoff.calendarPopup() is True
    assert hv.btn_manual_trade.property("class") == "primary-btn"
    assert hv.btn_export.property("class") == "success-btn"
    assert hv.btn_exit.property("class") == "danger-btn"
    assert hv.btn_audit.text() == "All Trades"

    # Verify date sync between Tab 1 and Tab 2
    from PySide6.QtCore import QDate
    win.upload_view.date_filter.setDate(QDate(2025, 6, 15))
    assert hv.date_cutoff.date() == QDate(2025, 6, 15)

    win.close()


def test_account_manager_dialog(qapp, db_conn, monkeypatch):
    """Verify AccountManagerDialog lists accounts and adds new ones."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.Ok)

    dlg = AccountManagerDialog(db_conn)
    assert dlg.table.rowCount() == 2
    assert dlg.table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert not (dlg.table.item(0, 0).flags() & Qt.ItemIsEditable)

    # Add account via dialog
    dlg.txt_acc_id.setText("ZERODHA_SIS")
    dlg.txt_name.setText("Sister's Zerodha")
    dlg._on_add_account()

    assert dlg.table.rowCount() == 3

    # Test Edit Account button and EditAccountDialog
    assert hasattr(dlg, "btn_edit")
    from portfolio_tracker.ui.account_manager_dialog import EditAccountDialog
    edit_dlg = EditAccountDialog(db_conn, "ZERODHA_SIS", "Sister's Zerodha", "Zerodha", parent=dlg)
    edit_dlg.txt_acc_id.setText("ZERODHA_SISTER")
    edit_dlg.txt_name.setText("Sister Main Account")
    edit_dlg._on_save()

    dlg._load_accounts()
    acc_ids = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    assert "ZERODHA_SISTER" in acc_ids
    assert "ZERODHA_SIS" not in acc_ids

    edit_dlg.close()
    dlg.close()


def test_manual_trade_dialog(qapp, db_conn, monkeypatch):
    """Verify ManualTradeDialog inputs and validation."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.Ok)

    dlg = ManualTradeDialog(db_conn)

    # Empty symbol should prevent saving
    dlg.txt_symbol.setText("")
    dlg._on_save()

    # Invalid Quantity should prevent saving
    dlg.txt_symbol.setText("RELIANCE")
    dlg.txt_qty.setText("0")
    dlg._on_save()
    assert db_conn.execute("SELECT count(*) FROM transactions WHERE symbol = 'RELIANCE';").fetchone()[0] == 0

    # Invalid Price should prevent saving
    dlg.txt_qty.setText("25")
    dlg.txt_price.setText("-50.0")
    dlg._on_save()
    assert db_conn.execute("SELECT count(*) FROM transactions WHERE symbol = 'RELIANCE';").fetchone()[0] == 0

    # Valid entry with QLineEdit inputs and pure date picker
    dlg.txt_price.setText("2500.00")
    from PySide6.QtCore import QDate
    dlg.date_picker.setDate(QDate(2023, 5, 15))
    dlg._on_save()

    # Verify default notes options (IPO, Bonus/Split) and free text
    assert dlg.combo_notes is not None
    combo_items = [dlg.combo_notes.itemText(i) for i in range(dlg.combo_notes.count())]
    assert "IPO" in combo_items
    assert "Bonus/Split" in combo_items

    # Test preset buttons
    dlg.btn_preset_ipo.click()
    assert dlg.combo_notes.currentText() == "IPO"

    dlg.btn_preset_bonus.click()
    assert dlg.combo_notes.currentText() == "Bonus/Split"
    assert dlg.txt_price.text() == "0.00"

    # Test saving bonus trade with ₹0.00
    dlg.txt_symbol.setText("INFY")
    dlg.txt_qty.setText("50")
    dlg._on_save()
    row_bonus = db_conn.execute("SELECT quantity, price, notes FROM transactions WHERE symbol = 'INFY';").fetchone()
    assert row_bonus is not None
    assert row_bonus[0] == 50
    assert row_bonus[1] == 0.0
    assert row_bonus[2] == "Bonus/Split"

    # Test free text
    dlg.combo_notes.setEditText("Off-market DP transfer")
    assert dlg.combo_notes.currentText() == "Off-market DP transfer"
    assert dlg.txt_notes.text() == "Off-market DP transfer"

    # Check inserted row in DB and dedicated symbols table
    row = db_conn.execute("SELECT symbol, quantity, price, trade_date FROM transactions WHERE symbol = 'RELIANCE';").fetchone()
    assert row is not None
    assert row[0] == "RELIANCE"
    assert row[1] == 25
    assert row[2] == 2500.0
    assert "2023-05-15" in row[3]

    # Verify symbol autocomplete recommendation recorded
    sym_row = db_conn.execute("SELECT symbol FROM symbols WHERE symbol = 'RELIANCE';").fetchone()
    assert sym_row is not None
    assert sym_row[0] == "RELIANCE"

    # Verify completer is configured on txt_symbol
    assert dlg.completer is not None
    assert dlg.txt_symbol.completer() is dlg.completer

    dlg.close()


def test_chart_hover_banner_and_calendar_years(qapp, db_conn):
    """Verify chart inspection banner, bar hover, and calendar 2010-2040 year dropdown."""
    import pandas as pd
    from PySide6.QtWidgets import QCalendarWidget, QToolButton
    from portfolio_tracker.ui.charts import NativeChartView
    from portfolio_tracker.ui.styles import configure_modern_calendar

    # 1. Calendar 2010-2040 scrollable year dropdown test
    cal = QCalendarWidget()
    configure_modern_calendar(cal)
    year_btn = cal.findChild(QToolButton, "qt_calendar_yearbutton")
    assert year_btn is not None
    assert year_btn.menu() is not None

    list_w = getattr(year_btn, "_year_list_widget", None)
    assert list_w is not None
    assert list_w.count() == 31  # 2010 to 2040 inclusive
    assert list_w.item(0).text() == "2010"
    assert list_w.item(30).text() == "2040"
    assert list_w.maximumHeight() <= 200  # Compact scrollable bounded height

    # Clicking year_btn triggers instant popup menu without showing spinbox
    year_btn.click()
    year_edit = cal.findChild(QToolButton, "qt_calendar_yearedit")
    assert year_edit is None or not year_edit.isVisible()

    # 2. NativeChartView inspection banner and hover
    chart_view = NativeChartView()
    assert hasattr(chart_view, "lbl_hover_banner")
    assert "Hover over" in chart_view.lbl_hover_banner.text()

    sample_df = pd.DataFrame([
        {
            "symbol": "INFY",
            "quantity": 100,
            "avg_buy_price": 1400.0,
            "total_buy_cost": 140000.0,
            "net_capital_at_risk": 30000.0,
            "is_closed": False,
            "is_anomalous": False,
            "realized_pnl": 0.0,
        },
        {
            "symbol": "TCS",
            "quantity": 0,
            "avg_buy_price": 3200.0,
            "total_buy_cost": 320000.0,
            "net_capital_at_risk": 0.0,
            "is_closed": True,
            "is_anomalous": False,
            "realized_pnl": 45000.0,
        },
    ])
    chart_view.update_data(sample_df)

    # Hovering over donut slice updates banner
    series = chart_view.chart.series()[0]
    slice0 = series.slices()[0]
    slice0.hovered.emit(True)
    assert "INFY" in chart_view.lbl_hover_banner.text()
    assert "140,000.00" in chart_view.lbl_hover_banner.text()

    slice0.hovered.emit(False)
    assert "Hover over" in chart_view.lbl_hover_banner.text()

    # Test Capital Recovery Bar hover
    chart_view.combo_mode.setCurrentIndex(1)
    bar_series = chart_view.chart.series()[0]
    bar_set = bar_series.barSets()[0]
    bar_set.hovered.emit(True, 0)
    assert "INFY" in chart_view.lbl_hover_banner.text()
    assert "Actual Exposure" in chart_view.lbl_hover_banner.text()
    assert "Net Exposure" in chart_view.lbl_hover_banner.text()

    bar_set.hovered.emit(False, 0)
    assert "Hover over" in chart_view.lbl_hover_banner.text()

    cal.close()
    chart_view.close()


def test_segmented_chart_tabs_and_empty_return(qapp, db_conn):
    """Verify 1-click segmented chart tabs, combo sync, and empty state return action."""
    import pandas as pd
    from portfolio_tracker.ui.charts import NativeChartView

    chart_view = NativeChartView()

    # Verify 3 segmented tab buttons exist
    assert hasattr(chart_view, "btn_tab_donut")
    assert hasattr(chart_view, "btn_tab_bar")
    assert hasattr(chart_view, "btn_tab_realized")
    assert hasattr(chart_view, "btn_empty_action")
    # Dropdown is removed/hidden from user interface
    assert chart_view.combo_mode.isHidden() is True

    # Initial state is DONUT
    assert chart_view.current_mode == "DONUT"
    assert chart_view.btn_tab_donut.property("class") == "chart-tab-active"
    assert chart_view.btn_tab_bar.property("class") == "chart-tab"
    assert chart_view.btn_tab_realized.property("class") == "chart-tab"

    # Click BAR tab
    chart_view.btn_tab_bar.click()
    assert chart_view.current_mode == "BAR"
    assert chart_view.combo_mode.currentData() == "BAR"
    assert chart_view.btn_tab_bar.property("class") == "chart-tab-active"
    assert chart_view.btn_tab_donut.property("class") == "chart-tab"

    # Click REALIZED tab
    chart_view.btn_tab_realized.click()
    assert chart_view.current_mode == "REALIZED"
    assert chart_view.combo_mode.currentData() == "REALIZED"
    assert chart_view.btn_tab_realized.property("class") == "chart-tab-active"

    # Set mode via combo_mode dropdown
    idx_donut = chart_view.combo_mode.findData("DONUT")
    chart_view.combo_mode.setCurrentIndex(idx_donut)
    assert chart_view.current_mode == "DONUT"
    assert chart_view.btn_tab_donut.property("class") == "chart-tab-active"

    # Empty state action return button test
    active_only_df = pd.DataFrame([
        {
            "symbol": "INFY",
            "quantity": 100,
            "avg_buy_price": 1400.0,
            "total_buy_cost": 140000.0,
            "net_capital_at_risk": 30000.0,
            "is_closed": False,
            "is_anomalous": False,
            "realized_pnl": 0.0,
        }
    ])
    chart_view.update_data(active_only_df)
    # Switch to REALIZED with 0 closed positions
    chart_view.btn_tab_realized.click()
    assert chart_view.stack.currentIndex() == 1  # Empty placeholder visible
    assert not chart_view.btn_empty_action.isHidden()
    assert "Asset Allocation" in chart_view.btn_empty_action.text()

    # Click empty action button to seamlessly return to DONUT
    chart_view.btn_empty_action.click()
    assert chart_view.current_mode == "DONUT"
    assert chart_view.stack.currentIndex() == 0  # Chart visible again

    chart_view.close()


def test_table_sorting_and_interactive_resizing(qapp, db_conn):
    """Verify table column interactive resizing, auto-fit, and numeric sorting."""
    from PySide6.QtWidgets import QHeaderView
    from portfolio_tracker.ui.transaction_history_dialog import TransactionHistoryDialog

    # Seed transactions with varying quantities and costs
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "AAA_SMALL", "BUY", 10, 100.0, "2026-01-01")   # Cost 1k, Qty 10
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "BBB_LARGE", "BUY", 250, 1000.0, "2026-01-02") # Cost 250k, Qty 250
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "CCC_MID", "BUY", 50, 500.0, "2026-01-03")     # Cost 25k, Qty 50

    win = MainWindow(db_conn)
    hv = win.holdings_view
    hv.refresh_data()

    # 1. Verify HoldingsView table resizability & auto-fit
    header = hv.table.horizontalHeader()
    for col in range(hv.table.columnCount()):
        assert header.sectionResizeMode(col) == QHeaderView.Interactive
    assert header.stretchLastSection() is True
    assert hv.table.isSortingEnabled() is True
    assert hasattr(hv, "btn_autofit")

    # Run auto-fit
    hv.btn_autofit.click()
    assert header.stretchLastSection() is True

    # 2. Verify accurate numeric sorting on Shares Held (Col 1)
    hv.table.sortItems(1, Qt.AscendingOrder)
    col1_asc = [int(hv.table.item(r, 1).text().replace(",", "")) for r in range(hv.table.rowCount())]
    assert col1_asc == sorted(col1_asc)
    assert col1_asc == [10, 50, 250]

    hv.table.sortItems(1, Qt.DescendingOrder)
    col1_desc = [int(hv.table.item(r, 1).text().replace(",", "")) for r in range(hv.table.rowCount())]
    assert col1_desc == sorted(col1_desc, reverse=True)
    assert col1_desc == [250, 50, 10]

    # 3. Verify accurate numeric sorting on Deployed Cost (Col 2)
    hv.table.sortItems(2, Qt.AscendingOrder)
    col2_asc = [float(hv.table.item(r, 2).data(Qt.UserRole)) for r in range(hv.table.rowCount())]
    assert col2_asc == sorted(col2_asc)

    # 4. Verify TransactionHistoryDialog interactive resizing & numeric sorting
    dlg = TransactionHistoryDialog(db_conn)
    dlg_header = dlg.table.horizontalHeader()
    for col in range(dlg.table.columnCount()):
        assert dlg_header.sectionResizeMode(col) == QHeaderView.Interactive
    assert dlg_header.stretchLastSection() is True
    assert dlg.table.isSortingEnabled() is True
    assert hasattr(dlg, "btn_autofit")

    # Sort by Qty (Col 4)
    dlg.table.sortItems(4, Qt.AscendingOrder)
    qty_vals = [float(dlg.table.item(r, 4).data(Qt.UserRole)) for r in range(dlg.table.rowCount())]
    assert qty_vals == sorted(qty_vals)

    dlg.close()
    win.close()


def test_edit_trade_dialog_and_confirmation(qapp, db_conn, monkeypatch):
    """Verify EditTradeDialog inputs, mandatory note validation, confirmation tab comparison, and DB update."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.Ok)

    # 1. Insert starter trade
    trade_id = insert_manual_transaction(
        db_conn, "ZERODHA_SELF", "RELIANCE", "BUY", 50, 2400.0, "2024-01-15 10:00:00", notes="Initial buy"
    )

    # 2. Open EditTradeDialog
    dlg = EditTradeDialog(db_conn, trade_id)
    assert dlg.tabs.count() == 2
    assert dlg.tabs.currentIndex() == 0
    assert dlg.txt_symbol.text() == "RELIANCE"
    assert dlg.txt_qty.text() == "50"
    assert "2400" in dlg.txt_price.text()

    # 3. Test mandatory note validation: empty note should block advancing to confirmation tab
    dlg.combo_notes.setEditText("")
    dlg.btn_next.click()
    assert dlg.tabs.currentIndex() == 0  # Stayed on tab 0

    # 4. Use preset button
    dlg.combo_notes.setEditText("Stock Split adjustment")
    assert dlg.combo_notes.currentText() == "Stock Split adjustment"

    # 5. Modify quantity and price for a 1:2 split (shares double 50 -> 100, price halves 2400 -> 1200)
    dlg.txt_qty.setText("100")
    dlg.txt_price.setText("1200.00")

    # 6. Click Next: should advance to Confirmation tab (Tab 1)
    dlg.btn_next.click()
    assert dlg.tabs.currentIndex() == 1

    # Check comparison table rows
    assert dlg.table_compare.rowCount() >= 6
    labels = [dlg.table_compare.item(r, 0).text() for r in range(dlg.table_compare.rowCount())]
    assert "Quantity (Shares)" in labels
    qty_row = labels.index("Quantity (Shares)")
    assert dlg.table_compare.item(qty_row, 1).text() == "50"
    assert dlg.table_compare.item(qty_row, 2).text() == "100"
    assert "+50 shares" in dlg.table_compare.item(qty_row, 3).text()

    # Check Reason note callout
    assert "Stock Split adjustment" in dlg.lbl_confirm_reason.text()

    # 7. Test Back to Edit button
    dlg.btn_back.click()
    assert dlg.tabs.currentIndex() == 0

    # Advance back to confirmation
    dlg.btn_next.click()
    assert dlg.tabs.currentIndex() == 1

    # 8. Confirm & Save changes
    updated_signal = []
    dlg.trade_updated.connect(lambda tid: updated_signal.append(tid))
    dlg._save_changes()

    assert updated_signal == [trade_id]

    # Verify database was updated
    row = db_conn.execute("SELECT quantity, price, notes FROM transactions WHERE trade_id = ?;", (trade_id,)).fetchone()
    assert row[0] == 100
    assert row[1] == 1200.0
    assert row[2] == "Stock Split adjustment"

    dlg.close()

    # 9. Test TransactionHistoryDialog edit button
    audit_dlg = TransactionHistoryDialog(db_conn)
    assert hasattr(audit_dlg, "btn_edit")
    assert audit_dlg.btn_edit.property("class") == "primary-btn"

    # Clicking edit without selection shows message
    audit_dlg.btn_edit.click()

    # Select the row and trigger edit
    audit_dlg.table.selectRow(0)
    # Monkeypatch EditTradeDialog.exec so it simulates a successful edit without hanging
    edit_opened = []
    def fake_exec(self):
        edit_opened.append(self.trade_id)
        self.trade_updated.emit(self.trade_id)
        return 1

    monkeypatch.setattr(EditTradeDialog, "exec", fake_exec)

    audit_signal = []
    audit_dlg.transaction_updated.connect(lambda: audit_signal.append(True))
    audit_dlg._on_edit_selected()

    assert edit_opened == [trade_id]
    assert len(audit_signal) == 1

    audit_dlg.close()


def test_upload_view_confirmation_safety_layer(qapp, db_conn, tmp_path, monkeypatch):
    """Verify UploadView confirms 'X trades will be added to Y account' before committing."""
    from PySide6.QtWidgets import QMessageBox

    csv_path = tmp_path / "confirm_trades.csv"
    csv_path.write_text(
        "Trade Date,TradingSymbol,Trade Type,Quantity,Price,Trade ID\n"
        "2026-01-10 10:15:00,INFY,BUY,100,1500.50,CONF1001\n"
        "2026-01-12 11:30:00,TCS,BUY,50,3400.00,CONF1002\n",
        encoding="utf-8",
    )

    uv = UploadView(db_conn)
    uv.show()
    uv._set_selected_file(str(csv_path))
    assert uv.btn_import.isEnabled() is True

    # Scenario 1: User says "No" to confirmation
    questions_asked = []
    def mock_question(parent, title, text, buttons, default):
        questions_asked.append((title, text))
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", mock_question)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

    uv._start_import()

    # Verify confirmation was requested with '2' trades and target account
    assert len(questions_asked) == 1
    title, text = questions_asked[0]
    assert "Confirm Trade Import" in title
    assert "2" in text
    assert "will be added to account" in text

    # DB should have 0 transactions because user declined
    count = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count == 0
    # File is still selected so user doesn't have to re-browse
    assert uv.selected_file_path == str(csv_path)

    # Scenario 2: User says "Yes" to confirmation
    monkeypatch.setattr(QMessageBox, "question", lambda parent, title, text, buttons, default: QMessageBox.Yes)

    signals = []
    uv.import_completed.connect(lambda: signals.append(True))

    uv._start_import()

    # DB now has 2 transactions
    count_after = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count_after == 2
    assert len(signals) == 1
    assert uv.status_card.isVisible() is True
    assert "2 new transactions inserted" in uv.lbl_status_detail.text()

    # Scenario 3: User tries to re-import the same file (all duplicates)
    info_shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: info_shown.append((title, text)))
    uv._set_selected_file(str(csv_path))
    uv._start_import()

    # Should show "All Trades Already Imported" and not ask confirmation to add 0 trades
    assert any("Already Imported" in item[0] for item in info_shown)
    count_final = db_conn.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
    assert count_final == 2  # No duplicates inserted

    uv.close()



