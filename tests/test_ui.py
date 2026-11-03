"""Offscreen GUI tests for PySide6 MainWindow, HoldingsView, and Dialogs."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication

from portfolio_tracker.db import (
    add_symbol_mapping,
    get_pnl_adjustments,
    init_db,
    insert_dividend,
    insert_manual_transaction,
    insert_pnl_adjustment,
)
from portfolio_tracker.ui.account_manager_dialog import AccountManagerDialog
from portfolio_tracker.ui.edit_trade_dialog import EditTradeDialog
from portfolio_tracker.ui.main_window import MainWindow
from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
from portfolio_tracker.ui.pnl_adjustments_dialog import PnlAdjustmentsDialog
from portfolio_tracker.ui.transaction_history_dialog import TransactionHistoryDialog
from portfolio_tracker.ui.upload_view import UploadView


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "ui_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_main_window_tabs_and_structure(qapp, db_conn):
    """Verify MainWindow initializes with 4 tabs and correct branding."""
    win = MainWindow(db_conn)
    assert win.tabs.count() == 4
    assert "Holdings Dashboard" in win.tabs.tabText(0)
    assert "Import Tradebook" in win.tabs.tabText(1)
    assert "Dividends Dashboard" in win.tabs.tabText(2)
    assert "Import Dividends" in win.tabs.tabText(3)
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

    # Verify Table rows and 10 columns (with Dividends column hidden by default)
    assert hv.table.rowCount() == 2
    assert hv.table.columnCount() == 10
    assert hv.table.isColumnHidden(6) is True
    symbols = [hv.table.item(r, 0).text() for r in range(hv.table.rowCount())]
    assert "TCS" in symbols
    assert "INFY" in symbols

    # Check house money tooltip on INFY (Col 8: Effective Avg Price)
    infy_row = symbols.index("INFY")
    infy_avg_item = hv.table.item(infy_row, 8)
    assert "Risk Free" in infy_avg_item.text()
    assert "Pure House Money" in infy_avg_item.toolTip()
    assert "Cash Extracted" in infy_avg_item.toolTip()

    # Check INFY Col 5 Booked P&L and Col 7 Net Exposure
    infy_pnl_item = hv.table.item(infy_row, 5)
    assert "(+) ₹45,000.00" in infy_pnl_item.text()
    assert infy_pnl_item.foreground().color().name().upper() == "#047857"
    assert infy_pnl_item.background().color().name().upper() == "#DCFCE7"

    infy_net_item = hv.table.item(infy_row, 7)
    assert "Risk Free" in infy_net_item.text()
    assert infy_net_item.foreground().color().name().upper() == "#047857"
    assert infy_net_item.background().color().name().upper() == "#DCFCE7"

    # Check TCS: Actual Exposure (Col 4), Booked P&L (Col 5), Net Exposure (Col 7)
    tcs_row = symbols.index("TCS")
    tcs_act_item = hv.table.item(tcs_row, 4)
    assert "₹180,000.00" in tcs_act_item.text()

    tcs_pnl_item = hv.table.item(tcs_row, 5)
    assert "(+) ₹20,000.00" in tcs_pnl_item.text()
    assert tcs_pnl_item.foreground().color().name().upper() == "#047857"

    tcs_net_item = hv.table.item(tcs_row, 7)
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
    wipro_avg_item = hv.table.item(wipro_row, 8)
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

    # Verify initial empty fields and placeholders (no pre-filled defaults)
    assert dlg.txt_qty.text() == ""
    assert dlg.txt_price.text() == ""
    assert dlg.txt_qty.placeholderText() != ""
    assert dlg.txt_price.placeholderText() != ""

    # Empty symbol should prevent saving
    dlg.txt_symbol.setText("")
    dlg._on_save()

    # Empty quantity should prevent saving
    dlg.txt_symbol.setText("RELIANCE")
    dlg._on_save()
    assert db_conn.execute("SELECT count(*) FROM transactions WHERE symbol = 'RELIANCE';").fetchone()[0] == 0

    # Invalid Quantity should prevent saving
    dlg.txt_qty.setText("0")
    dlg._on_save()
    assert db_conn.execute("SELECT count(*) FROM transactions WHERE symbol = 'RELIANCE';").fetchone()[0] == 0

    # Empty price should prevent saving
    dlg.txt_qty.setText("25")
    dlg._on_save()
    assert db_conn.execute("SELECT count(*) FROM transactions WHERE symbol = 'RELIANCE';").fetchone()[0] == 0

    # Invalid Price should prevent saving
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
    """Verify 1-click segmented chart tabs, Top N selector, side legend, and collapsible container."""
    import pandas as pd
    from portfolio_tracker.ui.charts import NativeChartView
    from portfolio_tracker.ui.holdings_view import HoldingsView

    chart_view = NativeChartView()

    # Verify segmented tab buttons: Donut and Bar (Realized Profit removed as requested)
    assert hasattr(chart_view, "btn_tab_donut")
    assert hasattr(chart_view, "btn_tab_bar")
    assert not hasattr(chart_view, "btn_tab_realized")
    assert hasattr(chart_view, "btn_empty_action")
    assert hasattr(chart_view, "combo_top_n")
    assert chart_view.combo_top_n.count() == 4  # Top 5, Top 10, Top 20, Top 50

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
        }
    ])
    chart_view.update_data(sample_df)

    # Initial state is DONUT with side legend visible
    assert chart_view.current_mode == "DONUT"
    assert chart_view.btn_tab_donut.property("class") == "chart-tab-active"
    assert chart_view.btn_tab_bar.property("class") == "chart-tab"
    assert chart_view.legend_panel.isHidden() is False

    # Test with 12 distinct stocks
    multi_stocks = []
    for i in range(12):
        multi_stocks.append({
            "symbol": f"STOCK_{i}",
            "quantity": 10,
            "avg_buy_price": 100.0 * (i + 1),
            "total_buy_cost": 1000.0 * (i + 1),
            "net_capital_at_risk": 500.0 * (i + 1),
            "is_closed": False,
            "is_anomalous": False,
            "realized_pnl": 0.0,
        })
    multi_df = pd.DataFrame(multi_stocks)
    chart_view.update_data(multi_df)

    # Test Top 5 selector (5 stocks + 1 other = 6 slices & 6 legend items)
    idx_5 = chart_view.combo_top_n.findData(5)
    chart_view.combo_top_n.setCurrentIndex(idx_5)
    donut_series = chart_view.chart.series()[0]
    assert donut_series.count() == 6
    assert "Other (7 stocks" in donut_series.slices()[-1].label()
    assert chart_view.legend_grid.count() == 6

    # Test legend item hover interaction
    legend_item_0 = chart_view.legend_grid.itemAt(0).widget()
    slice_0 = donut_series.slices()[0]
    assert slice_0.isExploded() is False
    legend_item_0.hovered.emit(True)
    assert slice_0.isExploded() is True
    assert "STOCK_11" in chart_view.lbl_hover_banner.text()
    legend_item_0.hovered.emit(False)
    assert slice_0.isExploded() is False

    # Test Top 50 selector (shows all 12 stocks)
    idx_50 = chart_view.combo_top_n.findData(50)
    chart_view.combo_top_n.setCurrentIndex(idx_50)
    donut_series_50 = chart_view.chart.series()[0]
    assert donut_series_50.count() == 12
    assert chart_view.legend_grid.count() == 12

    # Click BAR tab
    chart_view.btn_tab_bar.click()
    assert chart_view.current_mode == "BAR"
    assert chart_view.combo_mode.currentData() == "BAR"
    assert chart_view.btn_tab_bar.property("class") == "chart-tab-active"
    assert chart_view.btn_tab_donut.property("class") == "chart-tab"
    assert chart_view.legend_panel.isHidden() is True

    # Click DONUT tab
    chart_view.btn_tab_donut.click()
    assert chart_view.current_mode == "DONUT"
    assert chart_view.legend_panel.isHidden() is False

    # Set mode via combo_mode dropdown
    idx_bar = chart_view.combo_mode.findData("BAR")
    chart_view.combo_mode.setCurrentIndex(idx_bar)
    assert chart_view.current_mode == "BAR"
    assert chart_view.btn_tab_bar.property("class") == "chart-tab-active"

    # Empty state test
    empty_df = pd.DataFrame()
    chart_view.update_data(empty_df)
    assert chart_view.stack.currentIndex() == 1  # Empty placeholder visible
    chart_view.close()

    # Verify HoldingsView collapsible chart section (default closed)
    hv = HoldingsView(db_conn)
    hv.show()
    assert hv.chart_body.isHidden() is True
    assert "▶ Show Visual Charts" in hv.btn_toggle_charts.text()

    # Click toggle button to expand
    hv.btn_toggle_charts.click()
    assert hv.chart_body.isHidden() is False
    assert "▼ Hide Visual Charts" in hv.btn_toggle_charts.text()

    # Click toggle button to collapse again
    hv.btn_toggle_charts.click()
    assert hv.chart_body.isHidden() is True
    assert "▶ Show Visual Charts" in hv.btn_toggle_charts.text()
    hv.close()


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


def test_transaction_history_dialog_unlimited_and_search(qapp, db_conn):
    """Verify TransactionHistoryDialog loads all trades without 300 limit and search finds older trades."""
    # Insert 320 trades (315 TCS + 5 AARTIDRUGS)
    for i in range(315):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "TCS", "BUY", 10, 3000.0, f"2023-01-01 00:00:{i%60:02d}"
        )
    for i in range(5):
        insert_manual_transaction(
            db_conn, "ZERODHA_SELF", "AARTIDRUGS", "BUY", 20, 450.0, f"2022-05-01 00:00:{i%60:02d}"
        )

    dlg = TransactionHistoryDialog(db_conn)
    dlg.show()

    # Verify all 320 trades are loaded (not capped at 300)
    assert dlg.table.rowCount() == 320
    assert "320 trade(s)" in dlg.lbl_count.text()

    # Search for AARTIDRUGS: should find all 5 trades even though they are older
    dlg.txt_search.setText("AARTIDRUGS")
    visible = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible) == 5
    assert "Showing 5 of 320 trade(s)" in dlg.lbl_count.text()

    for r in visible:
        assert dlg.table.item(r, 2).text() == "AARTIDRUGS"

    # Clear search
    dlg.txt_search.setText("")
    visible_all = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible_all) == 320

    dlg.close()


def test_holdings_table_search_and_double_click_navigation(qapp, db_conn, monkeypatch):
    """Verify Holdings table search bar filters rows by symbol/status, and double-click opens audit for script."""
    from PySide6.QtCore import QPoint
    from portfolio_tracker.ui.holdings_view import HoldingsView
    from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
    from portfolio_tracker.ui.transaction_history_dialog import TransactionHistoryDialog

    # 1. Seed database with multiple stocks
    # AARTIDRUGS: 5 buys, 1 sell
    for i in range(5):
        insert_manual_transaction(db_conn, "ZERODHA_SELF", "AARTIDRUGS", "BUY", 10, 400.0, f"2023-01-0{i+1}")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "AARTIDRUGS", "SELL", 20, 600.0, "2023-02-01")

    # RELIANCE: 2 buys
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RELIANCE", "BUY", 15, 2500.0, "2023-03-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "RELIANCE", "BUY", 10, 2600.0, "2023-03-05")

    # TCS: 1 buy
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "TCS", "BUY", 5, 3500.0, "2023-04-01")

    hv = HoldingsView(db_conn)
    hv.show()

    # Verify 3 stocks present in Holdings table
    assert hv.table.rowCount() == 3
    assert "3 stocks" in hv.lbl_holdings_count.text()

    # 2. Test Holdings table search filtering by symbol
    hv.txt_search_holdings.setText("AARTI")
    visible_rows = [r for r in range(hv.table.rowCount()) if not hv.table.isRowHidden(r)]
    assert len(visible_rows) == 1
    assert hv.table.item(visible_rows[0], 0).text() == "AARTIDRUGS"
    assert "Showing 1 of 3 stocks" in hv.lbl_holdings_count.text()

    # Clear search
    hv.txt_search_holdings.setText("")
    visible_all = [r for r in range(hv.table.rowCount()) if not hv.table.isRowHidden(r)]
    assert len(visible_all) == 3
    assert "3 stocks" in hv.lbl_holdings_count.text()

    # 3. Test Holdings table search filtering by status (e.g. "Active")
    hv.txt_search_holdings.setText("Active")
    visible_status = [r for r in range(hv.table.rowCount()) if not hv.table.isRowHidden(r)]
    assert len(visible_status) >= 1
    hv.txt_search_holdings.setText("")

    # 4. Test double click on holding row opens TransactionHistoryDialog with initial_search and show_adjustments=True
    audit_calls = []

    class MockAuditDlg:
        def __init__(self, *args, **kwargs):
            audit_calls.append(kwargs)
            self.transaction_deleted = type("DummySignal", (), {"connect": lambda self, fn: None})()
            self.transaction_updated = type("DummySignal", (), {"connect": lambda self, fn: None})()

        def exec(self):
            pass

    monkeypatch.setattr("portfolio_tracker.ui.holdings_view.TransactionHistoryDialog", MockAuditDlg)

    # Find row index for AARTIDRUGS
    aarti_row = None
    for r in range(hv.table.rowCount()):
        if "AARTIDRUGS" in hv.table.item(r, 0).text():
            aarti_row = r
            break
    assert aarti_row is not None

    # Simulate double-click on AARTIDRUGS row -> show_adjustments should be True
    hv._on_table_cell_double_clicked(aarti_row, 0)
    assert len(audit_calls) == 1
    assert audit_calls[-1]["initial_search"] == "AARTIDRUGS"
    assert audit_calls[-1]["show_adjustments"] is True

    # Simulate clicking general "All Trades" header button -> show_adjustments should be False
    hv.btn_audit.click()
    assert len(audit_calls) == 2
    assert audit_calls[-1]["initial_search"] == ""
    assert audit_calls[-1]["show_adjustments"] is False

    # 5. Verify TransactionHistoryDialog with initial_search and show_adjustments
    hist_dlg = TransactionHistoryDialog(db_conn, initial_search="AARTIDRUGS", show_adjustments=True)
    assert "AARTIDRUGS" in hist_dlg.windowTitle()
    assert hist_dlg.txt_search.text() == "AARTIDRUGS"
    assert hist_dlg.chk_show_adjustments.isChecked() is True
    hist_visible = [r for r in range(hist_dlg.table.rowCount()) if not hist_dlg.table.isRowHidden(r)]
    assert len(hist_visible) == 6  # 5 buys + 1 sell
    assert "Showing 6 of 9" in hist_dlg.lbl_count.text()
    hist_dlg.close()

    # Verify default TransactionHistoryDialog keeps adjustments unchecked
    hist_dlg_default = TransactionHistoryDialog(db_conn)
    assert hist_dlg_default.chk_show_adjustments.isChecked() is False
    hist_dlg_default.close()

    # 6. Verify ManualTradeDialog with initial_symbol pre-populates symbol field
    man_dlg = ManualTradeDialog(db_conn, initial_symbol="AARTIDRUGS")
    assert man_dlg.txt_symbol.text() == "AARTIDRUGS"
    man_dlg.close()

    # 7. Verify right-click context menu generates expected actions
    menu_actions = []

    def mock_show_context_menu(menu, pos):
        menu_actions.extend([act.text() for act in menu.actions()])

    monkeypatch.setattr(hv, "_show_context_menu", mock_show_context_menu)
    cell_rect = hv.table.visualItemRect(hv.table.item(aarti_row, 0))
    hv._on_table_context_menu(cell_rect.center())
    assert any("View All Trades for AARTIDRUGS" in act for act in menu_actions)
    assert any("Add Manual Trade for AARTIDRUGS" in act for act in menu_actions)
    assert any("Copy Symbol (AARTIDRUGS)" in act for act in menu_actions)

    hv.close()


def test_holdings_table_startup_alphabetical_symbol_sort(qapp, db_conn):
    """Verify that Holdings table at startup always sorts by symbol alphabetically ascending."""
    from portfolio_tracker.ui.holdings_view import HoldingsView

    # Insert transactions in non-alphabetical order
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "ZOMATO", "BUY", 100, 150.0, "2024-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "TCS", "BUY", 10, 3500.0, "2024-01-02")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "AARTIDRUGS", "BUY", 50, 450.0, "2024-01-03")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 30, 1600.0, "2024-01-04")

    hv = HoldingsView(db_conn)
    header = hv.table.horizontalHeader()
    assert header.sortIndicatorSection() == 0
    assert header.sortIndicatorOrder() == Qt.AscendingOrder

    # Verify rows in table are strictly in alphabetical ascending order: AARTIDRUGS, INFY, TCS, ZOMATO
    symbols = [hv.table.item(r, 0).text() for r in range(hv.table.rowCount())]
    assert symbols == ["AARTIDRUGS", "INFY", "TCS", "ZOMATO"]

    hv.close()


def test_upload_view_multiple_files_and_account_warning(qapp, db_conn, tmp_path, monkeypatch):
    """Verify UploadView multi-spreadsheet batch selection, account warning notice, and inter-file deduplication."""
    from PySide6.QtWidgets import QMessageBox

    # File 1: 2 trades (INFY, TCS)
    csv1 = tmp_path / "tradebook_fy23.csv"
    csv1.write_text(
        "Trade Date,TradingSymbol,Trade Type,Quantity,Price,Trade ID\n"
        "2023-01-10 10:15:00,INFY,BUY,100,1500.00,BATCH_01\n"
        "2023-01-12 11:30:00,TCS,BUY,50,3400.00,BATCH_02\n",
        encoding="utf-8",
    )

    # File 2: 2 trades (TCS duplicate of BATCH_02, plus new trade RELIANCE)
    csv2 = tmp_path / "tradebook_fy24.csv"
    csv2.write_text(
        "Trade Date,TradingSymbol,Trade Type,Quantity,Price,Trade ID\n"
        "2023-01-12 11:30:00,TCS,BUY,50,3400.00,BATCH_02\n"  # Duplicate from file 1!
        "2024-02-15 14:00:00,RELIANCE,BUY,20,2500.00,BATCH_03\n",
        encoding="utf-8",
    )

    uv = UploadView(db_conn)
    uv.show()

    # Step 1: Verify persistent account warning card is displayed in Step 1
    assert hasattr(uv, "account_warning_card")
    assert uv.account_warning_card.isVisible() is True
    assert "By default, all uploaded files in a batch will be credited to" in uv.lbl_account_warning.text()
    assert "Please ensure all selected spreadsheets belong to this same family account" in uv.lbl_account_warning.text()

    # Select both files
    uv._set_selected_files([str(csv1), str(csv2)])
    assert uv.btn_import.isEnabled() is True
    assert len(uv.selected_file_paths) == 2

    # Step 2: Verify file card reflects multi-file batch and shows account attribution warning
    assert "2 Tradebook Files Selected" in uv.lbl_file_name.text()
    assert "Ready for batch ingestion" in uv.lbl_file_meta.text()
    curr_acc_name = uv.combo_account.currentText()
    assert f"⚠️ All 2 files will be credited to account: {curr_acc_name}" in uv.lbl_file_account_notice.text()

    # Verify confirmation safety dialog prompts with explicit account warning
    questions_asked = []
    def mock_question(parent, title, text, buttons, default):
        questions_asked.append((title, text))
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "question", mock_question)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    signals = []
    uv.import_completed.connect(lambda: signals.append(True))

    uv._start_import()

    # Verify confirmation dialog content
    assert len(questions_asked) == 1
    title, prompt_text = questions_asked[0]
    assert "Confirm Trade Import" in title
    # 4 total trades across 2 files, with 1 duplicate skipped (TCS duplicate from File 2) -> 3 new trades to add
    assert "3 trade(s)" in prompt_text
    assert "1 duplicate trade(s) will be skipped" in prompt_text
    assert f"credited to account '{curr_acc_name}'" in prompt_text
    assert "⚠️ IMPORTANT: By default, all trades from these 2 spreadsheets will be credited" in prompt_text

    # Verify DB has 3 unique transactions (BATCH_01, BATCH_02, BATCH_03)
    rows = db_conn.execute("SELECT trade_id, symbol FROM transactions ORDER BY trade_id;").fetchall()
    assert len(rows) == 3
    assert rows[0][0] == "BATCH_01"
    assert rows[1][0] == "BATCH_02"
    assert rows[2][0] == "BATCH_03"

    # Verify status banner shows 2 files ingested and deduplication stats
    assert uv.status_card.isVisible() is True
    assert "Files Ingested: 2 spreadsheet(s)" in uv.lbl_status_detail.text()
    assert "Deduplicated: 1 duplicate entries automatically skipped" in uv.lbl_status_detail.text()
    assert len(signals) == 1

    uv.close()


def test_all_trades_symbol_mapping_dual_search_and_adjustments_toggle(qapp, db_conn):
    """Verify TransactionHistoryDialog supports dual canonical/historical search and toggling adjustments."""
    # Map PEL -> PIRAMALFIN
    add_symbol_mapping(db_conn, "PEL", "PIRAMALFIN", "Piramal Enterprises Renamed")

    # Seed 1 trade for PEL and 1 trade for PIRAMALFIN
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "PEL", "BUY", 10, 1000.0, "2023-01-01 10:00:00")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "PIRAMALFIN", "BUY", 10, 1200.0, "2024-01-01 10:00:00")

    # Seed 1 stock adjustment and 1 carried profit adjustment on TCS
    insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=15.93,
        adjustment_date="2024-01-02",
        category="BROKERAGE_CHARGES",
        direction="LOSS",
        symbol="PIRAMALFIN",
        notes="DP Charge on PIRAMALFIN",
    )
    insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=5000.0,
        adjustment_date="2022-12-31",
        category="CARRIED_FORWARD_PROFIT",
        direction="PROFIT",
        symbol="TCS",
        notes="Old Demat Lumpsum",
    )

    dlg = TransactionHistoryDialog(db_conn)

    # 1. Initially toggle is unchecked -> Only 2 trades shown
    assert dlg.chk_show_adjustments.isChecked() is False
    assert dlg.table.rowCount() == 2

    # Verify symbol mapping presentation on PEL: "PEL ➔ PIRAMALFIN"
    symbols = [dlg.table.item(r, 2).text() for r in range(dlg.table.rowCount())]
    assert "PEL ➔ PIRAMALFIN" in symbols
    assert "PIRAMALFIN" in symbols

    # 2. Dual Search Verification:
    # Query 'PIRAMALFIN' should match BOTH the mapped PEL trade and the native PIRAMALFIN trade
    dlg.txt_search.setText("PIRAMALFIN")
    visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible_rows) == 2

    # Query 'PEL' should ONLY match the historic PEL trade
    dlg.txt_search.setText("PEL")
    visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible_rows) == 1
    matched_sym = dlg.table.item(visible_rows[0], 2).text()
    assert matched_sym == "PEL ➔ PIRAMALFIN"

    # Reset search
    dlg.txt_search.clear()

    # 3. Check adjustments toggle -> 4 rows (2 trades + 2 adjustments)
    dlg.chk_show_adjustments.setChecked(True)
    assert dlg.table.rowCount() == 4

    types = [dlg.table.item(r, 3).text() for r in range(dlg.table.rowCount())]
    assert "BUY" in types
    assert "+ PROFIT" in types
    assert "- LOSS / CHG" in types

    # Search with adjustments active:
    # Query 'PIRAMALFIN' should show the 2 trades AND the DP charge adjustment on PIRAMALFIN
    dlg.txt_search.setText("PIRAMALFIN")
    visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible_rows) == 3

    # Query 'Old Demat' should show the account-wide adjustment
    dlg.txt_search.setText("Old Demat")
    visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert len(visible_rows) == 1
    assert "Old Demat" in dlg.table.item(visible_rows[0], 7).text()

    dlg.close()


def test_pnl_adjustments_dialog(qapp, db_conn, monkeypatch):
    """Verify PnlAdjustmentsDialog form validation, presets, ledger audit, and CRUD operations."""
    from PySide6.QtWidgets import QMessageBox

    info_messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: info_messages.append(args))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    dlg = PnlAdjustmentsDialog(db_conn, default_account_id="ZERODHA_SELF")

    # Initially ledger is empty
    assert dlg.table_ledger.rowCount() == 0

    # 1. Test Preset button
    dlg.btn_preset_brokerage.click()
    assert dlg.combo_category.currentData() == "BROKERAGE_CHARGES"
    assert dlg.radio_loss.isChecked() is True

    # 2. Fill form and save
    dlg.txt_amount.setText("1,250.50")
    dlg.txt_symbol.setText("INFY")
    dlg.txt_notes.setText("Brokerage and STT charges")
    dlg.btn_save.click()

    # Verify saved in DB
    adjs = get_pnl_adjustments(db_conn)
    assert len(adjs) == 1
    assert adjs[0]["amount"] == 1250.50
    assert adjs[0]["category"] == "BROKERAGE_CHARGES"
    assert adjs[0]["symbol"] == "INFY"
    assert adjs[0]["direction"] == "LOSS"

    # Verify ledger table has 1 row and tab switched to Ledger
    assert dlg.tabs.currentIndex() == 1
    assert dlg.table_ledger.rowCount() == 1

    # 3. Test Edit from Ledger
    dlg.table_ledger.selectRow(0)
    dlg.btn_edit_ledger.click()
    assert dlg.tabs.currentIndex() == 0
    assert dlg.editing_adjustment_id is not None
    assert dlg.btn_save.text() == "💾 Update Adjustment"
    assert dlg.txt_amount.text() == "1250.5"

    # Update amount to 1500.00
    dlg.txt_amount.setText("1500.00")
    dlg.btn_save.click()

    adjs = get_pnl_adjustments(db_conn)
    assert len(adjs) == 1
    assert adjs[0]["amount"] == 1500.00

    # 4. Test Delete from Ledger
    dlg.tabs.setCurrentIndex(1)
    dlg.table_ledger.selectRow(0)
    dlg.btn_delete_ledger.click()

    adjs = get_pnl_adjustments(db_conn)
    assert len(adjs) == 0
    assert dlg.table_ledger.rowCount() == 0

    dlg.close()


def test_holdings_view_adjustments_button_and_kpis(qapp, db_conn):
    """Verify HoldingsView displays P&L Adjustments button, adjusts Card 2 KPI, and provides tooltip breakdowns."""
    # Seed trade
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "TCS", "BUY", 100, 3000.0, "2026-01-01")

    # Seed stock-specific carried forward profit of 50,000 on TCS
    insert_pnl_adjustment(
        db_conn,
        account_id="ZERODHA_SELF",
        amount=50000.0,
        adjustment_date="2025-12-31",
        category="CARRIED_FORWARD_PROFIT",
        direction="PROFIT",
        symbol="TCS",
        notes="Old Demat",
    )

    win = MainWindow(db_conn)
    hv = win.holdings_view

    # Verify Adjustments button exists
    assert hasattr(hv, "btn_pnl_adjustments")
    assert "Adjust" in hv.btn_pnl_adjustments.text()

    hv.refresh_data()

    # Card 2 (Realized P&L) should reflect Trade P&L + Net Adjustments
    assert "50,000.00" in hv.card_extracted.value_label.text()
    assert "Adj: +₹50,000.00" in hv.card_extracted.sub_label.text()

    # TCS Row in Holdings Table
    assert hv.table.rowCount() == 1
    pnl_item = hv.table.item(0, 5)  # Col 5: Booked P&L
    assert "(+) ₹50,000.00" in pnl_item.text()
    assert "Carried Profit (Old Accounts): +₹50,000.00" in pnl_item.toolTip()
    assert "Stock Charges / Brokerage: -₹0.00" in pnl_item.toolTip()

    win.close()


def test_holdings_view_include_dividends_toggle(qapp, db_conn):
    """Verify HoldingsView include dividends toggle, total badge, column visibility, and risk calculation."""
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 100, 1000.0, "2025-01-01")
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "SELL", 50, 1200.0, "2025-02-01")
    insert_dividend(
        db_conn,
        account_id="ZERODHA_SELF",
        symbol="INFY",
        dividend_date="2025-03-01",
        amount=15000.0,
        quantity=50,
        dividend_per_share=300.0,
    )

    win = MainWindow(db_conn)
    win.show()
    hv = win.holdings_view
    hv.refresh_data()

    # 1. Baseline: Unchecked by default
    assert hv.chk_include_dividends.isChecked() is False
    assert hv.chk_include_dividends.text() == "Include Dividends"
    assert hv.card_dividends.isHidden() is True
    assert hv.table.isColumnHidden(6) is True
    assert hv.lbl_legend.text() == "Identity: Actual Exposure - Booked P&L = Net Exposure"
    assert "40,000.00" in hv.card_risk.value_label.text()
    assert "₹40,000.00" in hv.table.item(0, 7).text()  # Col 7: Net Exposure

    # 2. Checked: Opt-in dividends into risk calculation
    hv.chk_include_dividends.setChecked(True)
    assert hv.chk_include_dividends.isChecked() is True
    assert hv.card_dividends.isHidden() is False
    assert "15,000.00" in hv.card_dividends.value_label.text()
    assert "Total received until" in hv.card_dividends.sub_label.text()
    assert hv.table.isColumnHidden(6) is False
    assert "₹15,000.00" in hv.table.item(0, 6).text()  # Col 6: Dividends
    assert hv.lbl_legend.text() == "Identity: Actual Exposure - (Booked P&L + Dividends) = Net Exposure"
    assert "25,000.00" in hv.card_risk.value_label.text()
    assert "₹25,000.00" in hv.table.item(0, 7).text()  # Col 7: Net Exposure (50k - 10k - 15k)

    # 3. Revert: Uncheck
    hv.chk_include_dividends.setChecked(False)
    assert hv.card_dividends.isHidden() is True
    assert hv.table.isColumnHidden(6) is True
    assert hv.lbl_legend.text() == "Identity: Actual Exposure - Booked P&L = Net Exposure"
    assert "40,000.00" in hv.card_risk.value_label.text()
    assert "₹40,000.00" in hv.table.item(0, 7).text()

    win.close()


def test_transaction_history_dividends_visibility_and_ledger(qapp, db_conn):
    """Verify TransactionHistoryDialog conditional dividend checkbox, display, and dd-MM-yyyy date formatting."""
    insert_manual_transaction(db_conn, "ZERODHA_SELF", "INFY", "BUY", 100, 1000.0, "2025-01-10")
    insert_dividend(
        db_conn,
        account_id="ZERODHA_SELF",
        symbol="INFY",
        dividend_date="2025-06-15",
        amount=2500.0,
        quantity=100,
        dividend_per_share=25.0,
        remarks="Final Dividend",
    )

    # Case A: Directly opened via All Trades button (initial_search="") -> Checkbox MUST be hidden
    dlg_general = TransactionHistoryDialog(db_conn, initial_search="")
    dlg_general.show()
    assert dlg_general.chk_show_dividends.isHidden() is True
    assert dlg_general.table.rowCount() == 1
    dlg_general.close()

    # Case B: Opened for specific symbol from table row -> Checkbox MUST be visible
    dlg_sym = TransactionHistoryDialog(db_conn, initial_search="INFY")
    dlg_sym.show()
    assert dlg_sym.chk_show_dividends.isHidden() is False
    assert dlg_sym.chk_show_dividends.isChecked() is False
    assert dlg_sym.table.rowCount() == 1  # Only trade initially

    # Toggle Show Dividends
    dlg_sym.chk_show_dividends.setChecked(True)
    assert dlg_sym.table.rowCount() == 2

    # Find dividend row
    div_row = -1
    for r in range(dlg_sym.table.rowCount()):
        if dlg_sym.table.item(r, 3).text() == "DIVIDEND":
            div_row = r
            break

    assert div_row >= 0
    assert dlg_sym.table.item(div_row, 3).text() == "DIVIDEND"
    assert "100" in dlg_sym.table.item(div_row, 4).text()
    assert "₹25.00" in dlg_sym.table.item(div_row, 5).text()
    assert dlg_sym.table.item(div_row, 6).text() == "15-06-2025"  # dd-MM-yyyy format
    assert "Dividend Total: ₹2,500.00" in dlg_sym.table.item(div_row, 7).text()
    assert "Final Dividend" in dlg_sym.table.item(div_row, 7).text()

    dlg_sym.close()






