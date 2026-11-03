"""Audit dialog to view, search, and delete individual transactions."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from portfolio_tracker.db import (
    delete_pnl_adjustment,
    delete_transaction,
    get_accounts,
    get_all_symbols,
    get_pnl_adjustments,
    get_recent_transactions,
)
from portfolio_tracker.ui.edit_trade_dialog import EditTradeDialog
from portfolio_tracker.ui.pnl_adjustments_dialog import PnlAdjustmentsDialog
from portfolio_tracker.ui.styles import NumericTableWidgetItem, set_style_class


class TransactionHistoryDialog(QDialog):
    """Audit dialog to inspect transaction history, edit trade details, and delete accidental trades."""

    transaction_deleted = Signal()
    transaction_updated = Signal()

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        account_id: Optional[str] = None,
        initial_search: str = "",
        show_adjustments: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.db_conn = db_conn
        self.account_id = account_id
        self.initial_search = (initial_search or "").strip()
        self.initial_show_adjustments = bool(show_adjustments)
        title_suffix = f" - {self.initial_search}" if self.initial_search else ""
        self.setWindowTitle(f"All Trades{title_suffix}")
        self.setMinimumSize(900, 540)
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

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 12px; "
            "padding: 3px 10px; font-size: 12px; font-weight: 600; color: #475569;"
        )
        top_layout.addWidget(self.lbl_count)

        top_layout.addStretch()

        # Account Filter Combobox
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        self.combo_account.addItem("All Accounts (Consolidated)", None)
        try:
            accounts = get_accounts(self.db_conn)
            for acc in accounts:
                self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])
        except Exception:
            pass

        if self.account_id:
            idx = self.combo_account.findData(self.account_id)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)

        self.combo_account.currentIndexChanged.connect(lambda: self._filter_table())
        top_layout.addWidget(self.combo_account)

        # Show / Hide Adjustments Toggle
        self.chk_show_adjustments = QCheckBox("Show P&L Adjustments")
        self.chk_show_adjustments.setToolTip("Include carried-forward profits/losses and brokerage charges in the ledger")
        self.chk_show_adjustments.setChecked(self.initial_show_adjustments)
        self.chk_show_adjustments.stateChanged.connect(lambda: self._load_transactions())
        top_layout.addWidget(self.chk_show_adjustments)

        # Search Bar with Symbol Autocomplete
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search symbol (e.g. AARTIDRUGS), trade ID, note...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedWidth(280)
        symbols = get_all_symbols(self.db_conn)
        self.completer = QCompleter(symbols, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.txt_search.setCompleter(self.completer)
        self.txt_search.textChanged.connect(lambda: self._filter_table())
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
        self.table.cellDoubleClicked.connect(lambda row, col: self._on_edit_selected())
        layout.addWidget(self.table)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_edit = QPushButton("✏️ Edit Selected Trade")
        set_style_class(self.btn_edit, "primary-btn")
        self.btn_edit.clicked.connect(self._on_edit_selected)
        btn_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete Selected Transaction")
        set_style_class(self.btn_delete, "danger-btn")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        if self.initial_search:
            self.txt_search.setText(self.initial_search)

    def _auto_fit_columns(self):
        """Auto-fit column widths while keeping resizability intact."""
        self.table.resizeColumnsToContents()
        min_widths = [110, 120, 130, 85, 65, 95, 110, 200]
        for col, min_w in enumerate(min_widths):
            if col < self.table.columnCount():
                if self.table.columnWidth(col) < min_w:
                    self.table.setColumnWidth(col, min_w)
        self.table.horizontalHeader().setStretchLastSection(True)

    def _on_edit_selected(self):
        """Open the Edit Trade dialog or P&L Adjustments manager for the selected row."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Row", "Please select a transaction or adjustment to edit.")
            return

        row_idx = selected_rows[0].row()
        item_id = self.table.item(row_idx, 0)
        entry_type = item_id.data(Qt.UserRole + 2) if item_id else "TRADE"

        if entry_type == "ADJUSTMENT":
            try:
                dlg = PnlAdjustmentsDialog(self.db_conn, default_account_id=self.account_id, parent=self)
                dlg.adjustments_changed.connect(self._on_trade_updated)
                dlg.tabs.setCurrentIndex(1)  # Open directly to ledger tab
                dlg.exec()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open adjustments manager:\n{e}")
        else:
            trade_id = item_id.text()
            try:
                dlg = EditTradeDialog(self.db_conn, trade_id, parent=self)
                dlg.trade_updated.connect(self._on_trade_updated)
                dlg.exec()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open trade editor:\n{e}")

    def _on_trade_updated(self, *args):
        """Handle successful trade or adjustment update."""
        self._load_transactions()
        self.transaction_updated.emit()

    def _load_transactions(self):
        """Fetch all transactions and optionally P&L adjustments, populating table with numeric sorting."""
        self.table.setSortingEnabled(False)

        # 1. Fetch trades
        txs = get_recent_transactions(self.db_conn, account_id=None, limit=None)
        combined_entries = [
            {"entry_type": "TRADE", "data": t, "sort_date": str(t["trade_date"])}
            for t in txs
        ]

        # 2. Fetch adjustments if toggle is checked
        if hasattr(self, "chk_show_adjustments") and self.chk_show_adjustments.isChecked():
            try:
                adjs = get_pnl_adjustments(self.db_conn, account_id=None, limit=None)
                for a in adjs:
                    combined_entries.append({
                        "entry_type": "ADJUSTMENT",
                        "data": a,
                        "sort_date": str(a["adjustment_date"]),
                    })
            except Exception:
                pass

        # Sort entries chronologically descending
        combined_entries.sort(key=lambda x: x["sort_date"], reverse=True)
        self.table.setRowCount(len(combined_entries))

        for r_idx, entry in enumerate(combined_entries):
            e_type = entry["entry_type"]
            item_data = entry["data"]

            if e_type == "TRADE":
                t = item_data
                trade_id_str = str(t["trade_id"])
                it_id = NumericTableWidgetItem(trade_id_str)
                try:
                    it_id.setData(Qt.UserRole, int(trade_id_str))
                except ValueError:
                    it_id.setData(Qt.UserRole, trade_id_str)
                it_id.setData(Qt.UserRole + 2, "TRADE")
                it_id.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 0, it_id)

                # Account
                it_acc = NumericTableWidgetItem(str(t["user_name"]))
                it_acc.setData(Qt.UserRole, str(t["account_id"]))
                it_acc.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_acc.setFlags(it_acc.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 1, it_acc)

                # Symbol (Canonical & Original Corporate Action Awareness)
                orig_sym = str(t.get("original_symbol") or t["symbol"])
                canon_sym = str(t.get("canonical_symbol") or t["symbol"])
                is_mapped = bool(t.get("is_mapped") and orig_sym != canon_sym)

                if is_mapped:
                    sym_display = f"{orig_sym} ➔ {canon_sym}"
                    it_sym = NumericTableWidgetItem(sym_display)
                    it_sym.setToolTip(
                        f"Original Trade Symbol: {orig_sym}\n"
                        f"Mapped Canonical Symbol: {canon_sym}\n"
                        "Cost basis and holdings are tracked under the canonical symbol."
                    )
                else:
                    it_sym = NumericTableWidgetItem(orig_sym)

                it_sym.setData(Qt.UserRole, canon_sym)
                it_sym.setData(Qt.UserRole + 1, orig_sym)
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

            else:
                # ADJUSTMENT ROW
                a = item_data
                adj_id_str = str(a["adjustment_id"])
                it_id = NumericTableWidgetItem(adj_id_str)
                it_id.setData(Qt.UserRole, adj_id_str)
                it_id.setData(Qt.UserRole + 2, "ADJUSTMENT")
                it_id.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 0, it_id)

                # Account
                it_acc = NumericTableWidgetItem(str(a["user_name"]))
                it_acc.setData(Qt.UserRole, str(a["account_id"]))
                it_acc.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_acc.setFlags(it_acc.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 1, it_acc)

                # Symbol
                raw_sym = a.get("symbol")
                orig_sym = str(a.get("original_symbol") or raw_sym or "")
                canon_sym = str(a.get("canonical_symbol") or raw_sym or "")
                if raw_sym:
                    if a.get("is_mapped") and orig_sym != canon_sym:
                        sym_display = f"{orig_sym} ➔ {canon_sym}"
                    else:
                        sym_display = orig_sym
                else:
                    sym_display = "— (Account-Wide)"

                it_sym = NumericTableWidgetItem(sym_display)
                it_sym.setData(Qt.UserRole, canon_sym)
                it_sym.setData(Qt.UserRole + 1, orig_sym)
                it_sym.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_sym.setFlags(it_sym.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 2, it_sym)

                # Type Badge (🟢 + PROFIT / 🔴 - LOSS / CHG)
                is_profit = a["direction"] == "PROFIT"
                type_display = "+ PROFIT" if is_profit else "- LOSS / CHG"
                it_type = NumericTableWidgetItem(type_display)
                it_type.setTextAlignment(Qt.AlignCenter)
                if is_profit:
                    it_type.setForeground(QColor("#047857"))
                else:
                    it_type.setForeground(QColor("#B91C1C"))
                font_b = it_type.font()
                font_b.setBold(True)
                it_type.setFont(font_b)
                it_type.setFlags(it_type.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 3, it_type)

                # Quantity (dash for adjustments)
                it_qty = NumericTableWidgetItem("—")
                it_qty.setData(Qt.UserRole, 0.0)
                it_qty.setTextAlignment(Qt.AlignCenter)
                it_qty.setFlags(it_qty.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 4, it_qty)

                # Amount / Price
                amt_val = float(a["amount"])
                amt_signed = amt_val if is_profit else -amt_val
                amt_display = f"+₹{amt_val:,.2f}" if is_profit else f"-₹{amt_val:,.2f}"
                it_amt = NumericTableWidgetItem(amt_display)
                it_amt.setData(Qt.UserRole, amt_signed)
                it_amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if is_profit:
                    it_amt.setForeground(QColor("#047857"))
                else:
                    it_amt.setForeground(QColor("#B91C1C"))
                font_amt = it_amt.font()
                font_amt.setBold(True)
                it_amt.setFont(font_amt)
                it_amt.setFlags(it_amt.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 5, it_amt)

                # Date
                date_str = str(a["adjustment_date"])[:19]
                it_date = NumericTableWidgetItem(date_str)
                it_date.setData(Qt.UserRole, date_str)
                it_date.setTextAlignment(Qt.AlignCenter)
                it_date.setFlags(it_date.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 6, it_date)

                # Notes (Category + Description)
                cat_label = str(a["category"]).replace("_", " ").title()
                memo = str(a.get("notes") or "").strip()
                notes_text = f"[{cat_label}] {memo}".strip() if memo else f"[{cat_label}]"
                it_notes = NumericTableWidgetItem(notes_text)
                it_notes.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_notes.setFlags(it_notes.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 7, it_notes)

        self.table.setSortingEnabled(True)
        self._auto_fit_columns()
        self._filter_table()

    def _filter_table(self):
        if not hasattr(self, "table") or self.table is None:
            return
        query = self.txt_search.text().strip().lower()
        selected_acc = self.combo_account.currentData() if hasattr(self, "combo_account") else self.account_id

        visible_count = 0
        total_count = self.table.rowCount()

        for row in range(total_count):
            sym_item = self.table.item(row, 2)
            sym_display = sym_item.text().lower() if sym_item else ""
            canon_sym = str(sym_item.data(Qt.UserRole) or "").lower() if sym_item else ""
            orig_sym = str(sym_item.data(Qt.UserRole + 1) or "").lower() if sym_item else ""

            acc_name = self.table.item(row, 1).text().lower()
            acc_id = str(self.table.item(row, 1).data(Qt.UserRole) or "").lower()
            trade_id = self.table.item(row, 0).text().lower()
            tx_type = self.table.item(row, 3).text().lower()
            price_str = self.table.item(row, 5).text().lower()
            notes = self.table.item(row, 7).text().lower()

            acc_match = True
            if selected_acc:
                acc_match = (acc_id == str(selected_acc).lower())

            text_match = True
            if query:
                text_match = (
                    (query in sym_display)
                    or (query in canon_sym)
                    or (query in orig_sym)
                    or (query in acc_name)
                    or (query in acc_id)
                    or (query in trade_id)
                    or (query in tx_type)
                    or (query in price_str)
                    or (query in notes)
                )

            match = acc_match and text_match
            self.table.setRowHidden(row, not match)
            if match:
                visible_count += 1

        entity_name = "entry/entries" if (hasattr(self, "chk_show_adjustments") and self.chk_show_adjustments.isChecked()) else "trade(s)"
        if visible_count == total_count:
            self.lbl_count.setText(f"{total_count:,} {entity_name}")
        else:
            self.lbl_count.setText(f"Showing {visible_count:,} of {total_count:,} {entity_name}")

    def _on_delete_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Row", "Please select a transaction or adjustment to delete.")
            return

        row_idx = selected_rows[0].row()
        item_id = self.table.item(row_idx, 0)
        entry_type = item_id.data(Qt.UserRole + 2) if item_id else "TRADE"

        if entry_type == "ADJUSTMENT":
            adj_id = str(item_id.data(Qt.UserRole))
            sym = self.table.item(row_idx, 2).text()
            cat = self.table.item(row_idx, 7).text()
            amt = self.table.item(row_idx, 5).text()

            msg = (
                f"Are you sure you want to delete this P&L adjustment?\n\n"
                f"Adjustment ID: {adj_id}\n"
                f"Symbol/Scope: {sym}\n"
                f"Amount: {amt}\n"
                f"Details: {cat}\n\n"
                "This will update your portfolio cost basis and ledger immediately."
            )

            reply = QMessageBox.question(
                self,
                "Confirm Adjustment Deletion",
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                success = delete_pnl_adjustment(self.db_conn, adj_id)
                if success:
                    self._load_transactions()
                    self.transaction_deleted.emit()
                    QMessageBox.information(self, "Deleted", "P&L adjustment deleted successfully.")
                else:
                    QMessageBox.critical(self, "Error", "Could not delete adjustment.")
        else:
            trade_id = item_id.text()
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

