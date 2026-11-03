"""Holdings Dashboard: top controls, executive KPI cards, offline Plotly charts, and holdings table."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import QDate, QStringListModel, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import get_accounts, get_all_symbols
from portfolio_tracker.engine import get_holdings, get_portfolio_summary
from portfolio_tracker.exporter import export_portfolio_to_excel
from portfolio_tracker.ui.account_manager_dialog import AccountManagerDialog
from portfolio_tracker.ui.charts import NativeChartView
from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
from portfolio_tracker.ui.pnl_adjustments_dialog import PnlAdjustmentsDialog
from portfolio_tracker.ui.storage_settings_dialog import StorageSettingsDialog
from portfolio_tracker.ui.styles import (
    NumericTableWidgetItem,
    configure_modern_calendar,
    set_style_class,
)
from portfolio_tracker.ui.symbol_mapping_dialog import SymbolMappingDialog
from portfolio_tracker.ui.transaction_history_dialog import TransactionHistoryDialog


class HoldingsView(QWidget):
    """Main Portfolio Holdings View with senior-friendly layouts and high-contrast typography."""

    data_changed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.current_holdings_df = pd.DataFrame()
        self._init_ui()
        self.refresh_accounts()
        self.refresh_data()
        # Ensure Holdings table at startup always sorts by Stock Symbol (Col 0) alphabetically ascending
        self.table.sortByColumn(0, Qt.AscendingOrder)

    def _init_ui(self):
        # Root layout with QScrollArea for responsive scrolling on all screen sizes
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("holdings_scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            "QScrollArea#holdings_scroll_area { border: none; background: transparent; }"
            "QWidget#holdings_content_widget { background: transparent; }"
        )

        content_widget = QWidget()
        content_widget.setObjectName("holdings_content_widget")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(18, 16, 18, 24)
        main_layout.setSpacing(16)

        # ----------------------------------------------------
        # 1. Top Controls Bar (2-Row Modern Responsive Header)
        # ----------------------------------------------------
        controls_frame = QFrame()
        controls_frame.setObjectName("controls_frame")
        controls_frame.setStyleSheet(
            "QFrame#controls_frame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        # Row 1: Primary View Filters and Primary Actions
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(8)

        # Account Selector
        lbl_acc = QLabel("Portfolio:")
        lbl_acc.setStyleSheet("font-weight: 600; color: #334155;")
        row1_layout.addWidget(lbl_acc)

        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        self.combo_account.setMinimumWidth(210)
        self.combo_account.currentIndexChanged.connect(self.refresh_data)
        row1_layout.addWidget(self.combo_account)

        # Accounts Manager Button
        self.btn_manage_accounts = QPushButton("Accounts")
        self.btn_manage_accounts.setToolTip("Manage individual family members and Demat accounts")
        self.btn_manage_accounts.clicked.connect(self._open_account_manager)
        row1_layout.addWidget(self.btn_manage_accounts)

        # Symbol Mapping Button (Corporate Actions / Rebranding)
        self.btn_symbol_mapping = QPushButton("Symbol Mapping")
        self.btn_symbol_mapping.setToolTip("Map renamed stock tickers (e.g. CADILAHC → ZYDUSLIFE) to unify cost basis")
        self.btn_symbol_mapping.clicked.connect(self._open_symbol_mapping)
        row1_layout.addWidget(self.btn_symbol_mapping)

        row1_layout.addSpacing(4)

        # Cutoff Date Picker
        lbl_date = QLabel("As of Date:")
        lbl_date.setStyleSheet("font-weight: 600; color: #334155;")
        row1_layout.addWidget(lbl_date)

        self.date_cutoff = QDateEdit()
        self.date_cutoff.setDate(QDate.currentDate())
        self.date_cutoff.setCalendarPopup(True)
        configure_modern_calendar(self.date_cutoff.calendarWidget())
        self.date_cutoff.setDisplayFormat("yyyy-MM-dd")
        self.date_cutoff.setMinimumWidth(120)
        self.date_cutoff.setToolTip("Filter portfolio holdings and transactions up to this date")
        self.date_cutoff.dateChanged.connect(self.refresh_data)
        row1_layout.addWidget(self.date_cutoff)

        row1_layout.addSpacing(4)

        # Closed Positions Toggle
        self.chk_closed = QCheckBox("Show Closed Positions")
        self.chk_closed.setChecked(False)
        self.chk_closed.setToolTip("Display completely exited stock positions and their realized P&L")
        self.chk_closed.stateChanged.connect(self.refresh_data)
        row1_layout.addWidget(self.chk_closed)

        row1_layout.addStretch()

        # Row 1 Right: Primary Actions
        self.btn_manual_trade = QPushButton("+ Add Trade")
        set_style_class(self.btn_manual_trade, "primary-btn")
        self.btn_manual_trade.setToolTip("Record off-market, IPO, corporate action, or manual trade")
        self.btn_manual_trade.clicked.connect(lambda: self._open_manual_trade())
        row1_layout.addWidget(self.btn_manual_trade)

        self.btn_pnl_adjustments = QPushButton("⚖️ Adjust P&L")
        self.btn_pnl_adjustments.setStyleSheet("padding: 7px 11px;")
        self.btn_pnl_adjustments.setToolTip("Record stock-specific carried-forward profit/loss or brokerage charges")
        self.btn_pnl_adjustments.clicked.connect(lambda: self._open_pnl_adjustments())
        row1_layout.addWidget(self.btn_pnl_adjustments)

        controls_layout.addLayout(row1_layout)

        # Row 2: Secondary Utilities and Application Status
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(10)

        self.lbl_status = QLabel("Stock ACB Tracking • Offline Zerodha Multi-Account Ledger")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 500;")
        row2_layout.addWidget(self.lbl_status)

        row2_layout.addStretch()

        self.btn_audit = QPushButton("All Trades")
        self.btn_audit.setToolTip("Inspect all transaction records, filter by symbol, or delete entries")
        self.btn_audit.clicked.connect(lambda: self._open_transaction_audit())
        row2_layout.addWidget(self.btn_audit)

        self.btn_export = QPushButton("Export Excel")
        set_style_class(self.btn_export, "success-btn")
        self.btn_export.setToolTip("Export multi-tab formatted Excel report (Consolidated + Accounts)")
        self.btn_export.clicked.connect(self._export_to_excel)
        row2_layout.addWidget(self.btn_export)

        controls_layout.addLayout(row2_layout)

        main_layout.addWidget(controls_frame)

        # ----------------------------------------------------
        # 2. Executive KPI Cards Bar
        # ----------------------------------------------------
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(14)

        # Card 1: Total Net Exposure
        self.card_risk = self._create_kpi_card("Total Net Exposure", "₹0.00", "Adjusted Cost Basis (ACB) capital at risk")
        kpi_layout.addWidget(self.card_risk)

        # Card 2: Total Booked Profit
        self.card_extracted = self._create_kpi_card("Total Booked Profit", "₹0.00", "Realized profits from sales across portfolio")
        kpi_layout.addWidget(self.card_extracted)

        # Card 3: Active Holdings
        self.card_stocks = self._create_kpi_card("Active Holdings", "0 Stocks", "0 risk-free positions (ACB ₹0)")
        kpi_layout.addWidget(self.card_stocks)

        # Card 4: Closed Positions PnL
        self.card_closed = self._create_kpi_card("Closed Positions Profit", "₹0.00", "0 exited positions")
        kpi_layout.addWidget(self.card_closed)

        main_layout.addLayout(kpi_layout)

        # ----------------------------------------------------
        # 3. Full-Width Holdings Table (9 Columns)
        # ----------------------------------------------------
        table_container = QFrame()
        table_container.setObjectName("table_container")
        table_container.setStyleSheet(
            "QFrame#table_container { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(14, 14, 14, 14)
        table_layout.setSpacing(10)

        tbl_hdr = QHBoxLayout()
        table_title = QLabel("Holdings & Adjusted Cost Basis (ACB) Ledger")
        table_title.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 15px;")
        tbl_hdr.addWidget(table_title)

        self.lbl_holdings_count = QLabel("")
        self.lbl_holdings_count.setStyleSheet(
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 10px; "
            "padding: 2px 8px; font-size: 11px; font-weight: 600; color: #475569; margin-left: 6px;"
        )
        tbl_hdr.addWidget(self.lbl_holdings_count)

        tbl_hdr.addStretch()

        lbl_legend = QLabel("Identity: Actual Exposure - Booked P&L = Net Exposure")
        lbl_legend.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 500;")
        tbl_hdr.addWidget(lbl_legend)
        tbl_hdr.addSpacing(10)

        self.txt_search_holdings = QLineEdit()
        self.txt_search_holdings.setPlaceholderText("🔍 Search symbol or status...")
        self.txt_search_holdings.setClearButtonEnabled(True)
        self.txt_search_holdings.setFixedWidth(230)
        self.holdings_completer = QCompleter([], self)
        self.holdings_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.holdings_completer.setFilterMode(Qt.MatchContains)
        self.holdings_completer.setCompletionMode(QCompleter.PopupCompletion)
        popup = self.holdings_completer.popup()
        popup.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px; color: #0F172A;"
        )
        self.txt_search_holdings.setCompleter(self.holdings_completer)
        self.txt_search_holdings.textChanged.connect(self._filter_holdings_table)
        tbl_hdr.addWidget(self.txt_search_holdings)
        tbl_hdr.addSpacing(6)

        self.btn_autofit = QPushButton("↔ Auto-Fit")
        self.btn_autofit.setToolTip("Auto-fit column widths to fit content while preserving user drag resizing")
        self.btn_autofit.clicked.connect(self._auto_fit_columns)
        tbl_hdr.addWidget(self.btn_autofit)

        table_layout.addLayout(tbl_hdr)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Stock Symbol",
            "Shares Held",
            "Total Buy Cost (₹)",
            "Total Proceeds (₹)",
            "Actual Exposure (₹)",
            "Booked P&L (₹)",
            "Net Exposure (₹)",
            "Effective Avg Price (₹)",
            "Status / Flag",
        ])
        header = self.table.horizontalHeader()
        header.setToolTip("Click any column header to sort. Drag column dividers to resize.")
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        header_tooltips = [
            "Stock Ticker (NSE/BSE). Unifies historical ticker name changes if mapped.",
            "Remaining shares currently held (Buy Qty - Sell Qty).",
            "Total capital spent purchasing shares (Σ Buy Qty × Price).",
            "Total revenue received from selling shares (Σ Sell Qty × Price).",
            "Original purchase cost of currently held shares (Shares Held × Avg Buy Price).",
            "Realized profit or loss booked from sales so far. (+) Green = Profit, (-) Red = Loss.",
            "Adjusted Cost Basis (ACB): Actual Exposure minus Booked P&L. When ₹0.00, position is completely Risk Free (House Money)!",
            "Effective cost per share after profit offsets (Net Exposure / Shares Held). ₹0.00 indicates zero downside risk.",
            "Position status: Active Holding, Risk Free (House Money), Closed, or Anomalous.",
        ]
        for c_idx, tip in enumerate(header_tooltips):
            header_item = self.table.horizontalHeaderItem(c_idx)
            if header_item:
                header_item.setToolTip(tip)

        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 140)
        self.table.setColumnWidth(7, 160)
        self.table.setColumnWidth(8, 170)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(280)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setToolTip(
            "💡 Tip: Double-click any row to view all trades for that stock. Right-click for more options."
        )
        self.table.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        table_layout.addWidget(self.table)

        main_layout.addWidget(table_container)

        # ----------------------------------------------------
        # 4. Full-Width Chart View (Positioned Below Table)
        # ----------------------------------------------------
        chart_container = QFrame()
        chart_container.setObjectName("chart_container")
        chart_container.setStyleSheet(
            "QFrame#chart_container { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        chart_container.setMinimumHeight(440)
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(12, 12, 12, 12)

        self.chart_view = NativeChartView()
        chart_layout.addWidget(self.chart_view)

        main_layout.addWidget(chart_container)

        # Connect scroll area to root
        self.scroll_area.setWidget(content_widget)
        root_layout.addWidget(self.scroll_area)

    def _create_kpi_card(self, title: str, initial_val: str, initial_sub: str) -> QFrame:
        card = QFrame()
        set_style_class(card, "kpi-card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        lbl_title = QLabel(title)
        set_style_class(lbl_title, "kpi-title")
        layout.addWidget(lbl_title)

        lbl_val = QLabel(initial_val)
        set_style_class(lbl_val, "kpi-value")
        card.value_label = lbl_val  # Reference for dynamic updates
        layout.addWidget(lbl_val)

        lbl_sub = QLabel(initial_sub)
        set_style_class(lbl_sub, "kpi-subtext")
        card.sub_label = lbl_sub
        layout.addWidget(lbl_sub)

        return card

    def refresh_accounts(self):
        """Reload accounts into the top portfolio selector dropdown."""
        current_data = self.combo_account.currentData()
        self.combo_account.blockSignals(True)
        self.combo_account.clear()

        # Option 1: Consolidated Family View
        self.combo_account.addItem("Consolidated Family View", None)

        # Option 2+: Individual Accounts
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])

        # Restore previous selection if possible
        idx = self.combo_account.findData(current_data)
        if idx >= 0:
            self.combo_account.setCurrentIndex(idx)
        else:
            self.combo_account.setCurrentIndex(0)

        self.combo_account.blockSignals(False)

    def refresh_data(self):
        """Query engine and refresh KPIs, table, and charts."""
        account_id = self.combo_account.currentData()
        cutoff_qdate = self.date_cutoff.date()
        cutoff_str = f"{cutoff_qdate.year():04d}-{cutoff_qdate.month():02d}-{cutoff_qdate.day():02d} 23:59:59"
        include_closed = self.chk_closed.isChecked()

        # Query analytical engine
        df = get_holdings(
            db_conn=self.db_conn,
            cutoff_date=cutoff_str,
            account_id=account_id,
            include_closed=include_closed,
        )
        self.current_holdings_df = df

        # Update KPI Cards
        summary = get_portfolio_summary(
            df,
            db_conn=self.db_conn,
            account_id=account_id,
            cutoff_date=cutoff_str,
        )

        # Card 1: Total Net Exposure
        net_exposure_val = summary.get("total_net_exposure", summary.get("total_net_capital_at_risk", 0.0))
        if net_exposure_val > 0:
            self.card_risk.value_label.setText(f"₹{net_exposure_val:,.2f}")
            self.card_risk.value_label.setStyleSheet("color: #0F172A;")
        else:
            self.card_risk.value_label.setText("₹0.00 (Risk Free)")
            self.card_risk.value_label.setStyleSheet("color: #047857;")

        # Card 2: Total Booked Profit (Comprehensive Net Realized P&L including Adjustments & Brokerage)
        net_realized_val = summary.get("total_net_realized_pnl", summary.get("total_booked_profit", 0.0))
        if net_realized_val > 0:
            self.card_extracted.value_label.setText(f"(+) ₹{net_realized_val:,.2f}")
            self.card_extracted.value_label.setStyleSheet("color: #047857;")
        elif net_realized_val < 0:
            self.card_extracted.value_label.setText(f"(-) ₹{abs(net_realized_val):,.2f}")
            self.card_extracted.value_label.setStyleSheet("color: #DC2626;")
        else:
            self.card_extracted.value_label.setText("₹0.00")
            self.card_extracted.value_label.setStyleSheet("color: #0F172A;")

        adj_count = summary.get("adjustments_count", 0)
        if adj_count > 0:
            trade_pnl = summary.get("total_trade_booked_pnl", 0.0)
            net_adj = summary.get("total_net_adjustments", 0.0)
            sign_adj = "+" if net_adj >= 0 else "-"
            self.card_extracted.sub_label.setText(
                f"Trades: ₹{trade_pnl:,.2f} • Adj: {sign_adj}₹{abs(net_adj):,.2f}"
            )
        else:
            self.card_extracted.sub_label.setText("Realized profits from sales across portfolio")

        # Card 3: Active Holdings
        self.card_stocks.value_label.setText(f"{summary['active_stocks_count']} Stocks")
        self.card_stocks.sub_label.setText(f"{summary['risk_free_stocks_count']} risk-free positions (ACB ₹0)")

        # Card 4: Closed Positions Profit
        closed_pnl_val = summary["total_realized_pnl_closed"]
        if closed_pnl_val > 0:
            self.card_closed.value_label.setText(f"(+) ₹{closed_pnl_val:,.2f}")
            self.card_closed.value_label.setStyleSheet("color: #047857;")
        elif closed_pnl_val < 0:
            self.card_closed.value_label.setText(f"(-) ₹{abs(closed_pnl_val):,.2f}")
            self.card_closed.value_label.setStyleSheet("color: #DC2626;")
        else:
            self.card_closed.value_label.setText("₹0.00")
            self.card_closed.value_label.setStyleSheet("color: #0F172A;")

        self.card_closed.sub_label.setText(f"{summary['closed_stocks_count']} closed positions")

        # Update Table
        self._populate_table(df)

        # Update Native Chart
        self.chart_view.update_data(df)

    def _auto_fit_columns(self):
        """Auto-fit column widths to contents while keeping them interactive and resizable."""
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _populate_table(self, df: pd.DataFrame):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(df))

        for r_idx, row in df.iterrows():
            # 0. Stock Symbol (with indicator if mapped from older tickers)
            sym_str = str(row["symbol"])
            mapped_sources = row.get("mapped_sources", [])
            has_mapped = bool(mapped_sources and len(mapped_sources) > 0)
            sym_display = f"{sym_str} 🔀" if has_mapped else sym_str

            sym_item = NumericTableWidgetItem(sym_display)
            sym_item.setData(Qt.UserRole, sym_str)
            sym_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            sym_item.setData(Qt.FontRole, sym_item.font())
            if has_mapped:
                sym_item.setToolTip(
                    f"Canonical Symbol: {sym_str}\n"
                    f"Mapped from historical tickers: {', '.join(mapped_sources)}"
                )
            self.table.setItem(r_idx, 0, sym_item)

            # 1. Shares Held
            qty_val = float(row["net_qty"])
            qty_item = NumericTableWidgetItem(f"{row['net_qty']:,}")
            qty_item.setData(Qt.UserRole, qty_val)
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r_idx, 1, qty_item)

            # 2. Total Buy Cost
            cost_val = float(row["total_buy_cost"])
            cost_item = NumericTableWidgetItem(f"₹{cost_val:,.2f}")
            cost_item.setData(Qt.UserRole, cost_val)
            cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r_idx, 2, cost_item)

            # 3. Total Proceeds
            proc_val = float(row["total_proceeds"])
            proc_item = NumericTableWidgetItem(f"₹{proc_val:,.2f}")
            proc_item.setData(Qt.UserRole, proc_val)
            proc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r_idx, 3, proc_item)

            # 4. Actual Exposure (Shares Held * Avg Buy Price)
            actual_val = float(row.get("actual_exposure", 0.0))
            actual_item = NumericTableWidgetItem(f"₹{actual_val:,.2f}")
            actual_item.setData(Qt.UserRole, actual_val)
            actual_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            avg_p = float(row.get("avg_buy_price", 0.0))
            actual_item.setToolTip(
                f"Actual Exposure: ₹{actual_val:,.2f}\n"
                f"Original purchase cost of {row['net_qty']:,} remaining shares @ avg buy price ₹{avg_p:,.2f}."
            )
            self.table.setItem(r_idx, 4, actual_item)

            # 5. Booked P&L (Realized profit/loss from sales so far + stock-specific adjustments)
            pnl_val = float(row.get("booked_pnl", row.get("realized_pnl", 0.0)))
            trade_pnl_val = float(row.get("trade_booked_pnl", pnl_val))
            stock_adj_val = float(row.get("stock_adj_pnl", 0.0))
            carried_profit_val = float(row.get("stock_carried_profit", 0.0))
            charges_val = float(row.get("stock_charges", 0.0))

            pnl_item = NumericTableWidgetItem()
            pnl_item.setData(Qt.UserRole, pnl_val)
            pnl_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if pnl_val > 0:
                pnl_item.setText(f"(+) ₹{pnl_val:,.2f}")
                pnl_item.setForeground(QColor("#047857"))  # Emerald Green
                pnl_item.setBackground(QColor("#DCFCE7"))  # High-contrast green fill
            elif pnl_val < 0:
                pnl_item.setText(f"(-) ₹{abs(pnl_val):,.2f}")
                pnl_item.setForeground(QColor("#DC2626"))  # Crimson Red
                pnl_item.setBackground(QColor("#FEE2E2"))  # High-contrast red fill
            else:
                pnl_item.setText("₹0.00")
                pnl_item.setForeground(QColor("#475569"))
                pnl_item.setBackground(QColor("#F1F5F9"))

            # Build detailed tooltip breakdown
            tip = f"Realized Booked P&L: ₹{pnl_val:,.2f}"
            if stock_adj_val != 0:
                tip += (
                    f"\n• Trade Realized Gains: ₹{trade_pnl_val:,.2f}"
                    f"\n• Carried Profit (Old Accounts): +₹{carried_profit_val:,.2f}"
                    f"\n• Stock Charges / Brokerage: -₹{charges_val:,.2f}"
                )
            elif pnl_val > 0:
                tip += "\nProfits extracted from sales so far."
            elif pnl_val < 0:
                tip += "\nLosses realized from sales so far."
            else:
                tip += "\nBreak-Even: No profit or loss booked."
            pnl_item.setToolTip(tip)

            font_bold_pnl = pnl_item.font()
            font_bold_pnl.setBold(True)
            pnl_item.setFont(font_bold_pnl)
            self.table.setItem(r_idx, 5, pnl_item)

            # 6. Net Exposure (Actual Exposure - Booked P&L, floored at 0.0)
            net_exp_val = float(row.get("net_exposure", 0.0))
            net_item = NumericTableWidgetItem()
            net_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            font_bold_net = net_item.font()
            font_bold_net.setBold(True)
            net_item.setFont(font_bold_net)

            if row["is_closed"]:
                net_item.setData(Qt.UserRole, 0.0)
                net_item.setText("₹0.00 (Closed)")
                net_item.setForeground(QColor("#64748B"))
                net_item.setToolTip("Position completely exited. Zero capital at risk.")
            elif row["is_house_money"] or net_exp_val <= 0:
                net_item.setData(Qt.UserRole, 0.0)
                net_item.setText("₹0.00 (Risk Free)")
                net_item.setForeground(QColor("#047857"))
                net_item.setBackground(QColor("#DCFCE7"))
                net_item.setToolTip(
                    f"Pure House Money (Risk Free)\n"
                    f"Net Capital Exposure: ₹0.00\n"
                    f"Actual Exposure (₹{actual_val:,.2f}) completely offset by Booked Profit (₹{pnl_val:,.2f})."
                )
            else:
                net_item.setData(Qt.UserRole, net_exp_val)
                net_item.setText(f"₹{net_exp_val:,.2f}")
                net_item.setForeground(QColor("#0F172A"))
                net_item.setToolTip(
                    f"Net Capital Exposure: ₹{net_exp_val:,.2f}\n"
                    f"Actual Exposure (₹{actual_val:,.2f}) minus Booked P&L (₹{pnl_val:,.2f})."
                )
            self.table.setItem(r_idx, 6, net_item)

            # 7. Effective Average & House Money Tooltip
            eff_item = NumericTableWidgetItem()
            eff_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            if row["is_closed"]:
                eff_item.setData(Qt.UserRole, 0.0)
                eff_item.setText("₹0.00")
                eff_item.setForeground(QColor("#64748B"))
                eff_item.setToolTip("Position closed / exited. Effective average is ₹0.00 until a new trade is added.")
            elif row["is_house_money"]:
                eff_item.setText("₹0.00 (Risk Free)")
                raw_val = row.get("raw_effective_avg")
                eff_item.setData(Qt.UserRole, float(raw_val) if raw_val is not None and not pd.isna(raw_val) else 0.0)
                tooltip_text = (
                    f"Pure House Money (Risk Free)\n"
                    f"Exact Negative Basis: ₹{raw_val:,.2f}/share\n"
                    f"Total Net Cash Extracted: ₹{row['cash_extracted']:,.2f}\n"
                    f"All original principal recovered + profit extracted."
                )
                eff_item.setToolTip(tooltip_text)
                eff_item.setForeground(QColor("#047857"))  # Emerald text
            elif row.get("effective_avg") is not None and not pd.isna(row.get("effective_avg")):
                eff_val = float(row["effective_avg"])
                eff_item.setData(Qt.UserRole, eff_val)
                eff_item.setText(f"₹{eff_val:,.2f}")
            else:
                eff_item.setData(Qt.UserRole, 0.0)
                eff_item.setText("₹0.00")

            self.table.setItem(r_idx, 7, eff_item)

            # 8. Status Badge Column
            status_item = NumericTableWidgetItem()
            if row["is_anomalous"]:
                status_item.setText("Alert: Sell > Buy (Anomalous)")
                status_item.setToolTip("Account has sell transactions without sufficient prior buy records.")
                status_item.setForeground(QColor("#B45309"))  # Amber
            elif row["is_house_money"]:
                status_item.setText("Risk Free (House Money)")
                status_item.setForeground(QColor("#047857"))
            elif row["is_closed"]:
                status_item.setText(f"Closed (P&L: ₹{row['realized_pnl']:,.2f})")
                status_item.setForeground(QColor("#64748B"))
            else:
                status_item.setText("Active Holding")

            status_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(r_idx, 8, status_item)

            # Ensure all cells in row are strictly read-only
            for c in range(9):
                it = self.table.item(r_idx, c)
                if it:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)

            # Subtle background color on anomalous or risk free rows (preserve Col 5 and Col 6 badges)
            if row["is_house_money"]:
                for c in range(9):
                    if c not in (5, 6):
                        self.table.item(r_idx, c).setBackground(QColor("#F0FDF4"))
            elif row["is_anomalous"]:
                for c in range(9):
                    if c not in (5, 6):
                        self.table.item(r_idx, c).setBackground(QColor("#FFFBEB"))

        self.table.setSortingEnabled(True)

        # Update symbol suggestions in the search bar completer
        if not df.empty and "symbol" in df.columns:
            symbols = sorted([str(s) for s in df["symbol"].dropna().unique().tolist()])
            self.holdings_completer.setModel(QStringListModel(symbols, self.holdings_completer))

        # Re-apply current search filter (or update stock count)
        self._filter_holdings_table()

    def _filter_holdings_table(self):
        """Filter holdings table rows by symbol or status and update count indicator."""
        query = self.txt_search_holdings.text().strip().lower()
        total_rows = self.table.rowCount()
        visible_count = 0

        for r in range(total_rows):
            sym_item = self.table.item(r, 0)
            status_item = self.table.item(r, 8)

            sym = ""
            if sym_item:
                raw_sym = sym_item.data(Qt.UserRole)
                sym = (str(raw_sym) if raw_sym else sym_item.text()).lower()

            status = status_item.text().lower() if status_item else ""

            match = (not query) or (query in sym) or (query in status)
            self.table.setRowHidden(r, not match)
            if match:
                visible_count += 1

        if query:
            self.lbl_holdings_count.setText(f"Showing {visible_count} of {total_rows} stocks")
        else:
            self.lbl_holdings_count.setText(f"{total_rows} stocks" if total_rows > 0 else "")

    def _on_table_cell_double_clicked(self, row: int, col: int):
        """Double-clicking any holding row opens All Trades filtered to that symbol."""
        symbol_item = self.table.item(row, 0)
        if not symbol_item:
            return
        raw_sym = symbol_item.data(Qt.UserRole)
        symbol = str(raw_sym).strip() if raw_sym else symbol_item.text().split()[0]
        if symbol:
            self._open_transaction_audit(symbol=symbol)

    def _on_table_context_menu(self, pos):
        """Context menu on right-click offering trade audit, manual trade, and symbol copy."""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        symbol_item = self.table.item(row, 0)
        if not symbol_item:
            return
        raw_sym = symbol_item.data(Qt.UserRole)
        symbol = str(raw_sym).strip() if raw_sym else symbol_item.text().split()[0]
        if not symbol:
            return

        menu = QMenu(self)
        act_trades = menu.addAction(f"📜 View All Trades for {symbol}")
        act_trades.triggered.connect(lambda: self._open_transaction_audit(symbol=symbol))

        act_manual = menu.addAction(f"➕ Add Manual Trade for {symbol}")
        act_manual.triggered.connect(lambda: self._open_manual_trade(symbol=symbol))

        act_adj = menu.addAction(f"⚖️ Add Adjustment for {symbol}")
        act_adj.triggered.connect(lambda: self._open_pnl_adjustments(symbol=symbol))

        menu.addSeparator()
        act_copy = menu.addAction(f"📋 Copy Symbol ({symbol})")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(symbol))

        self._show_context_menu(menu, self.table.viewport().mapToGlobal(pos))

    def _show_context_menu(self, menu: QMenu, global_pos):
        """Display popup context menu at global screen position."""
        menu.exec(global_pos)

    def _open_symbol_mapping(self):
        """Open corporate actions and symbol renaming mapping dialog."""
        dlg = SymbolMappingDialog(self.db_conn, self)
        dlg.mapping_changed.connect(self._on_trade_modified)
        dlg.exec()

    def _open_account_manager(self):
        dlg = AccountManagerDialog(self.db_conn, self)
        dlg.accounts_changed.connect(self._on_accounts_modified)
        dlg.exec()

    def _on_accounts_modified(self):
        self.refresh_accounts()
        self.refresh_data()
        self.data_changed.emit()

    def _open_manual_trade(self, symbol: Optional[str] = None):
        if not isinstance(symbol, str):
            symbol = ""
        acc_id = self.combo_account.currentData()
        dlg = ManualTradeDialog(self.db_conn, default_account_id=acc_id, initial_symbol=symbol, parent=self)
        dlg.trade_added.connect(self._on_trade_modified)
        dlg.exec()

    def _open_pnl_adjustments(self, symbol: Optional[str] = None):
        if not isinstance(symbol, str):
            symbol = ""
        acc_id = self.combo_account.currentData()
        dlg = PnlAdjustmentsDialog(self.db_conn, default_account_id=acc_id, initial_symbol=symbol, parent=self)
        dlg.adjustments_changed.connect(self._on_trade_modified)
        dlg.exec()

    def _open_transaction_audit(self, symbol: Optional[str] = None):
        has_symbol = bool(isinstance(symbol, str) and symbol.strip())
        clean_symbol = symbol.strip() if has_symbol else ""
        acc_id = self.combo_account.currentData()
        dlg = TransactionHistoryDialog(
            self.db_conn,
            account_id=acc_id,
            initial_search=clean_symbol,
            show_adjustments=has_symbol,
            parent=self,
        )
        dlg.transaction_deleted.connect(self._on_trade_modified)
        dlg.transaction_updated.connect(self._on_trade_modified)
        dlg.exec()

    def _open_storage_settings(self):
        dlg = StorageSettingsDialog(self.db_conn, self)
        dlg.db_reloaded.connect(self._on_trade_modified)
        dlg.exec()

    def _on_trade_modified(self):
        self.refresh_data()
        self.data_changed.emit()

    def _export_to_excel(self):
        default_name = f"Family_Portfolio_Report_{date.today().strftime('%Y%m%d')}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Formatted Excel Report",
            str(Path.home() / default_name),
            "Excel Workbook (*.xlsx);;All Files (*.*)",
        )
        if not save_path:
            return

        cutoff_qdate = self.date_cutoff.date()
        cutoff_str = f"{cutoff_qdate.year():04d}-{cutoff_qdate.month():02d}-{cutoff_qdate.day():02d} 23:59:59"
        include_closed = self.chk_closed.isChecked()

        try:
            resolved = export_portfolio_to_excel(
                db_conn=self.db_conn,
                file_path=save_path,
                cutoff_date=cutoff_str,
                include_closed=include_closed,
            )
            QMessageBox.information(
                self,
                "Export Complete",
                f"Multi-tab Excel report saved successfully to:\n{resolved}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not generate Excel report:\n{e}")

    @property
    def btn_exit(self):
        """Backward-compatibility property referencing the top bar Close button."""
        win = self.window()
        if hasattr(win, "btn_close"):
            return win.btn_close
        if not hasattr(self, "_btn_exit_fallback"):
            self._btn_exit_fallback = QPushButton("Close")
            set_style_class(self._btn_exit_fallback, "danger-btn")
        return self._btn_exit_fallback

    @property
    def btn_storage(self):
        """Backward-compatibility property referencing the top bar DB Settings button."""
        win = self.window()
        if hasattr(win, "btn_db_settings"):
            return win.btn_db_settings
        if not hasattr(self, "_btn_storage_fallback"):
            self._btn_storage_fallback = QPushButton("DB Settings")
        return self._btn_storage_fallback

