"""Audit dialog to view, search, and delete individual transactions."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from portfolio_tracker.db import delete_transaction, get_all_symbols, get_recent_transactions
from portfolio_tracker.ui.styles import NumericTableWidgetItem, set_style_class


class TransactionHistoryDialog(QDialog):
    """Audit dialog to inspect transaction history and delete individual accidental trades."""

    transaction_deleted = Signal()

    def __init__(self, db_conn: sqlite3.Connection, account_id: str = None, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.account_id = account_id
        self.setWindowTitle("All Trades")
        self.setMinimumSize(850, 520)
        self._init_ui()
        self._load_transactions()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        top_layout = QHBoxLayout()
        title = QLabel("All Trades")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        top_layout.addWidget(title)
        top_layout.addStretch()

        # Search Bar with Symbol Autocomplete
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search by symbol or account...")
        self.txt_search.setFixedWidth(260)
        symbols = get_all_symbols(self.db_conn)
        self.completer = QCompleter(symbols, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.txt_search.setCompleter(self.completer)
        self.txt_search.textChanged.connect(self._filter_table)
        top_layout.addWidget(self.txt_search)

        self.btn_autofit = QPushButton("↔ Auto-Fit")
        self.btn_autofit.setToolTip("Auto-fit columns while keeping user drag resizing")
        self.btn_autofit.clicked.connect(self._auto_fit_columns)
        top_layout.addWidget(self.btn_autofit)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Trade ID", "Account", "Symbol", "Type", "Qty", "Price (₹)", "Trade Date", "Notes"
        ])
        header = self.table.horizontalHeader()
        header.setToolTip("Click any column header to sort. Drag column dividers to resize.")
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 120)
        self.table.setColumnWidth(7, 180)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Actions
        btn_layout = QHBoxLayout()
        self.btn_delete = QPushButton("Delete Selected Transaction")
        set_style_class(self.btn_delete, "danger-btn")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _auto_fit_columns(self):
        """Auto-fit column widths while keeping resizability intact."""
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _load_transactions(self):
        """Fetch transactions from database and populate the table with numeric sorting."""
        self.table.setSortingEnabled(False)
        txs = get_recent_transactions(self.db_conn, account_id=self.account_id, limit=300)
        self.table.setRowCount(len(txs))

        for r_idx, t in enumerate(txs):
            # Trade ID
            trade_id_str = str(t["trade_id"])
            it_id = NumericTableWidgetItem(trade_id_str)
            try:
                it_id.setData(Qt.UserRole, int(trade_id_str))
            except ValueError:
                it_id.setData(Qt.UserRole, trade_id_str)
            it_id.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 0, it_id)

            # Account
            it_acc = NumericTableWidgetItem(str(t["user_name"]))
            it_acc.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_acc.setFlags(it_acc.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 1, it_acc)

            # Symbol
            it_sym = NumericTableWidgetItem(str(t["symbol"]))
            it_sym.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_sym.setFlags(it_sym.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 2, it_sym)

            # Type
            tx_type_str = str(t["transaction_type"]).upper()
            it_type = NumericTableWidgetItem(tx_type_str)
            it_type.setTextAlignment(Qt.AlignCenter)
            if tx_type_str == "BUY":
                it_type.setForeground(QColor("#2563EB"))
            else:
                it_type.setForeground(QColor("#059669"))
            it_type.setFlags(it_type.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 3, it_type)

            # Quantity
            qty_val = float(t["quantity"])
            it_qty = NumericTableWidgetItem(f"{t['quantity']:,}")
            it_qty.setData(Qt.UserRole, qty_val)
            it_qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_qty.setFlags(it_qty.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 4, it_qty)

            # Price
            price_val = float(t["price"])
            it_price = NumericTableWidgetItem(f"₹{price_val:,.2f}")
            it_price.setData(Qt.UserRole, price_val)
            it_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_price.setFlags(it_price.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 5, it_price)

            # Trade Date
            date_str = str(t["trade_date"])
            it_date = NumericTableWidgetItem(date_str)
            it_date.setData(Qt.UserRole, date_str)
            it_date.setTextAlignment(Qt.AlignCenter)
            it_date.setFlags(it_date.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 6, it_date)

            # Notes
            it_notes = NumericTableWidgetItem(str(t["notes"] or ""))
            it_notes.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_notes.setFlags(it_notes.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 7, it_notes)

        self.table.setSortingEnabled(True)

    def _filter_table(self, query: str):
        q = query.strip().lower()
        for row in range(self.table.rowCount()):
            symbol = self.table.item(row, 2).text().lower()
            account = self.table.item(row, 1).text().lower()
            trade_id = self.table.item(row, 0).text().lower()
            match = (q in symbol) or (q in account) or (q in trade_id)
            self.table.setRowHidden(row, not match)

    def _on_delete_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Trade", "Please select a transaction to delete.")
            return

        row_idx = selected_rows[0].row()
        trade_id = self.table.item(row_idx, 0).text()
        symbol = self.table.item(row_idx, 2).text()
        tx_type = self.table.item(row_idx, 3).text()
        qty = self.table.item(row_idx, 4).text()
        price = self.table.item(row_idx, 5).text()

        msg = (
            f"Are you sure you want to delete this transaction?\n\n"
            f"Trade ID: {trade_id}\n"
            f"{tx_type} {qty} shares of {symbol} @ {price}\n\n"
            "This will update your cost basis and holdings immediately."
        )

        reply = QMessageBox.question(
            self,
            "Confirm Transaction Deletion",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success = delete_transaction(self.db_conn, trade_id)
            if success:
                self._load_transactions()
                self.transaction_deleted.emit()
                QMessageBox.information(self, "Deleted", "Transaction deleted successfully.")
            else:
                QMessageBox.critical(self, "Error", "Could not delete transaction.")

