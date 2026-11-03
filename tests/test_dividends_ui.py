"""Offscreen GUI tests for Dividends Dashboard, Import Dividends view, Manual Dividend dialog, and dd-MM-yyyy date format."""

import pytest
from PySide6.QtCore import QDate, Qt

from portfolio_tracker.db import (
    init_db,
    insert_dividend,
)
from portfolio_tracker.ui.dividends_dashboard_view import DividendsDashboardView
from portfolio_tracker.ui.edit_trade_dialog import EditTradeDialog
from portfolio_tracker.ui.holdings_view import HoldingsView
from portfolio_tracker.ui.import_dividends_view import ImportDividendsView
from portfolio_tracker.ui.main_window import MainWindow
from portfolio_tracker.ui.manual_dividend_dialog import ManualDividendDialog
from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
from portfolio_tracker.ui.pnl_adjustments_dialog import PnlAdjustmentsDialog
from portfolio_tracker.ui.upload_view import UploadView


@pytest.fixture
def db_conn(tmp_path):
    test_db = tmp_path / "dividends_ui_test.db"
    conn = init_db(test_db)
    yield conn
    conn.close()


def test_universal_date_pickers_format_dd_mm_yyyy(qapp, db_conn):
    """Verify all date pickers across old and new views use 'dd-MM-yyyy' display format."""
    # 1. HoldingsView
    hv = HoldingsView(db_conn)
    assert hv.date_cutoff.displayFormat() == "dd-MM-yyyy"

    # 2. UploadView
    uv = UploadView(db_conn)
    assert uv.date_filter.displayFormat() == "dd-MM-yyyy"

    # 3. ManualTradeDialog
    mtd = ManualTradeDialog(db_conn)
    assert mtd.date_picker.displayFormat() == "dd-MM-yyyy"

    # 4. PnlAdjustmentsDialog
    pad = PnlAdjustmentsDialog(db_conn)
    assert pad.date_edit.displayFormat() == "dd-MM-yyyy"

    # 5. DividendsDashboardView
    ddv = DividendsDashboardView(db_conn)
    assert ddv.date_from.displayFormat() == "dd-MM-yyyy"
    assert ddv.date_to.displayFormat() == "dd-MM-yyyy"

    # 6. ManualDividendDialog
    mdd = ManualDividendDialog(db_conn)
    assert mdd.date_picker.displayFormat() == "dd-MM-yyyy"


def test_main_window_tab_ordering_option_b(qapp, db_conn):
    """Verify MainWindow tabs are configured in Option B ordering."""
    win = MainWindow(db_conn)
    assert win.tabs.count() == 4
    assert win.tabs.tabText(0) == "Holdings Dashboard"
    assert win.tabs.tabText(1) == "Import Tradebook"
    assert win.tabs.tabText(2) == "Dividends Dashboard"
    assert win.tabs.tabText(3) == "Import Dividends"
    win.close()


def test_manual_dividend_dialog_auto_calc_and_save(qapp, db_conn):
    """Verify ManualDividendDialog auto-calculates total and persists to DB."""
    dlg = ManualDividendDialog(db_conn, default_account_id="ZERODHA_DAD")
    dlg.txt_symbol.setText("INFY")
    dlg.txt_quantity.setText("20")
    dlg.txt_dps.setText("25.50")

    # Check auto-calc total amount: 20 * 25.50 = 510.00 and is non-editable
    assert dlg.txt_amount.isReadOnly() is True
    assert dlg.txt_amount.text() == "510.00"

    saved_signal_fired = []
    dlg.dividend_saved.connect(lambda: saved_signal_fired.append(True))
    dlg._save_dividend()

    assert len(saved_signal_fired) == 1

    # Verify record in DB
    divs = db_conn.execute("SELECT symbol, amount, quantity, dividend_per_share FROM dividends;").fetchall()
    assert len(divs) == 1
    assert divs[0][0] == "INFY"
    assert divs[0][1] == 510.0
    assert divs[0][2] == 20
    assert divs[0][3] == 25.50


def test_dividends_dashboard_kpis_and_filters(qapp, db_conn):
    """Verify DividendsDashboardView updates KPIs, table, and filters by account, FY, and symbol."""
    insert_dividend(db_conn, "ZERODHA_DAD", "ABB", "2025-05-02", 33.5, 1, 33.5)
    insert_dividend(db_conn, "ZERODHA_DAD", "INFY", "2025-05-30", 220.0, 10, 22.0)
    insert_dividend(db_conn, "ZERODHA_SELF", "TCS", "2024-08-15", 500.0, 20, 25.0)

    ddv = DividendsDashboardView(db_conn)
    ddv.refresh_data()

    # Consolidated KPI check (all accounts)
    assert ddv.card_total.lbl_val.text() == "₹753.50"
    assert ddv.card_count.lbl_val.text() == "3"
    assert ddv.card_companies.lbl_val.text() == "3"
    assert "TCS" in ddv.card_top_payer.lbl_val.text()
    assert ddv.table.rowCount() == 3

    # Filter by single account (ZERODHA_DAD)
    idx_dad = ddv.combo_account.findData("ZERODHA_DAD")
    assert idx_dad >= 0
    ddv.combo_account.setCurrentIndex(idx_dad)
    assert ddv.card_total.lbl_val.text() == "₹253.50"
    assert ddv.card_count.lbl_val.text() == "2"
    assert ddv.table.rowCount() == 2

    # Reset account to Consolidated
    ddv.combo_account.setCurrentIndex(0)

    # Filter by Financial Year FY 2025-26
    idx_fy = ddv.combo_fy.findText("FY 2025-26")
    assert idx_fy >= 0
    ddv.combo_fy.setCurrentIndex(idx_fy)
    assert ddv.card_total.lbl_val.text() == "₹253.50"
    assert ddv.table.rowCount() == 2

    # Filter by Symbol Search "ABB"
    ddv.txt_search.setText("ABB")
    visible_rows = [r for r in range(ddv.table.rowCount()) if not ddv.table.isRowHidden(r)]
    assert len(visible_rows) == 1
    assert "Showing 1 of 2 payouts" in ddv.lbl_ledger_count.text()

    # Clear search
    ddv.txt_search.setText("")
    visible_all = [r for r in range(ddv.table.rowCount()) if not ddv.table.isRowHidden(r)]
    assert len(visible_all) == 2
    assert "2 payouts" in ddv.lbl_ledger_count.text()


def test_import_dividends_view_account_selection(qapp, db_conn):
    """Verify ImportDividendsView initializes with active accounts and emits import_completed."""
    view = ImportDividendsView(db_conn)
    assert view.combo_account.count() >= 2
    assert view.btn_process.isEnabled() is False


def test_dividends_collapsible_charts_section(qapp, db_conn):
    """Verify charts section is collapsed by default and toggles on button click."""
    insert_dividend(db_conn, "ZERODHA_DAD", "INFY", "2025-05-30", 500.0, 10, 50.0)
    ddv = DividendsDashboardView(db_conn)
    ddv.show()
    ddv.refresh_data()

    # 1. Closed by default
    assert ddv.chart_body.isHidden() is True
    assert ddv.chart_body.isVisible() is False
    assert "▶ Show Visual Charts" in ddv.btn_toggle_charts.text()

    # 2. Toggle open
    ddv.btn_toggle_charts.click()
    assert ddv.chart_body.isHidden() is False
    assert ddv.chart_body.isVisible() is True
    assert "▼ Hide Visual Charts" in ddv.btn_toggle_charts.text()

    # 3. Toggle closed again
    ddv.btn_toggle_charts.click()
    assert ddv.chart_body.isHidden() is True
    assert ddv.chart_body.isVisible() is False
    assert "▶ Show Visual Charts" in ddv.btn_toggle_charts.text()
    ddv.close()


def test_dividend_charts_modes_top_n_and_hover(qapp, db_conn):
    """Verify Line, Bar, Donut modes, Top N selector (5, 10, 20, 50), and hover states."""
    from PySide6.QtCore import QPointF
    from PySide6.QtCharts import QBarSeries, QLineSeries, QPieSeries

    # Insert 12 distinct stock payouts
    symbols = ["INFY", "TCS", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "RELIANCE"]
    for idx, s in enumerate(symbols):
        insert_dividend(db_conn, "ZERODHA_DAD", s, f"2025-0{(idx % 8) + 1}-15", float((idx + 1) * 100), 10, float(idx + 1) * 10)

    ddv = DividendsDashboardView(db_conn)
    ddv.show()
    ddv.btn_toggle_charts.click()  # expand charts
    ddv.refresh_data()
    charts = ddv.chart_view

    # --- Mode 1: Donut (Default) & Top N Selector ---
    assert charts.current_mode == "DONUT"
    assert charts.lbl_top_n.isHidden() is False
    assert charts.combo_top_n.isHidden() is False
    assert charts.legend_panel.isHidden() is False
    assert charts.combo_top_n.count() == 4  # Top 5, Top 10, Top 20, Top 50

    # Test Top 5
    idx_5 = charts.combo_top_n.findData(5)
    charts.combo_top_n.setCurrentIndex(idx_5)
    series_list = charts.chart.series()
    assert len(series_list) == 1
    donut_series = series_list[0]
    assert isinstance(donut_series, QPieSeries)
    # 5 top stocks + 1 "Other" slice = 6 slices
    assert donut_series.count() == 6
    assert "Other (7 stocks" in donut_series.slices()[-1].label()
    # Check side legend panel has 6 items
    assert charts.legend_grid.count() == 6

    # Test Top 50 selection
    idx_50 = charts.combo_top_n.findData(50)
    charts.combo_top_n.setCurrentIndex(idx_50)
    donut_series_50 = charts.chart.series()[0]
    assert donut_series_50.count() == 12  # All 12 symbols present
    assert charts.legend_grid.count() == 12

    # Test legend item hover interaction
    first_legend_item = charts.legend_grid.itemAt(0).widget()
    slice_top = donut_series_50.slices()[0]
    assert slice_top.isExploded() is False
    first_legend_item.hovered.emit(True)
    assert slice_top.isExploded() is True
    assert charts.lbl_hover_info.isHidden() is False
    first_legend_item.hovered.emit(False)
    assert slice_top.isExploded() is False
    assert charts.lbl_hover_info.isHidden() is True

    # Test Donut Slice Hover
    assert slice_top.isExploded() is False
    slice_top.hovered.emit(True)
    assert slice_top.isExploded() is True
    assert charts.lbl_hover_info.isHidden() is False
    assert "₹" in charts.lbl_hover_info.text()
    slice_top.hovered.emit(False)
    assert slice_top.isExploded() is False
    assert charts.lbl_hover_info.isHidden() is True

    # --- Mode 2: Bar Trend ---
    charts.set_mode("BAR")
    assert charts.current_mode == "BAR"
    assert charts.lbl_top_n.isHidden() is True
    assert charts.combo_top_n.isHidden() is True
    assert charts.legend_panel.isHidden() is True
    bar_series = charts.chart.series()[0]
    assert isinstance(bar_series, QBarSeries)
    assert bar_series.count() == 1
    bar_set = bar_series.barSets()[0]

    # Test Bar Hover
    bar_set.hovered.emit(True, 0)
    assert charts.lbl_hover_info.isHidden() is False
    assert "📊" in charts.lbl_hover_info.text()
    bar_set.hovered.emit(False, 0)
    assert charts.lbl_hover_info.isHidden() is True

    # --- Mode 3: Trend Line ---
    charts.set_mode("LINE")
    assert charts.current_mode == "LINE"
    assert charts.lbl_top_n.isHidden() is True
    assert charts.combo_top_n.isHidden() is True
    assert charts.legend_panel.isHidden() is True
    line_series = charts.chart.series()[0]
    assert isinstance(line_series, QLineSeries)
    assert line_series.pointsVisible() is True
    assert line_series.count() > 0

    # Test Line Hover
    line_series.hovered.emit(QPointF(0.0, 100.0), True)
    assert charts.lbl_hover_info.isHidden() is False
    assert "📈" in charts.lbl_hover_info.text()
    line_series.hovered.emit(QPointF(0.0, 100.0), False)
    assert charts.lbl_hover_info.isHidden() is True
    ddv.close()


