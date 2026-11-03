"""Dialog for recording and managing P&L adjustments, carried-forward profits/losses, and brokerage charges."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import (
    delete_pnl_adjustment,
    get_accounts,
    get_adjustments_summary,
    get_all_symbols,
    get_pnl_adjustment,
    get_pnl_adjustments,
    insert_pnl_adjustment,
    update_pnl_adjustment,
)
from portfolio_tracker.ui.styles import (
    NumericTableWidgetItem,
    configure_modern_calendar,
    set_style_class,
)


class PnlAdjustmentsDialog(QDialog):
    """Manager dialog with 2 tabs: Add/Edit Adjustment and Adjustments Ledger Audit."""

    adjustments_changed = Signal()

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        default_account_id: Optional[str] = None,
        initial_symbol: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.db_conn = db_conn
        self.default_account_id = default_account_id
        self.initial_symbol = (initial_symbol or "").strip()
        self.editing_adjustment_id: Optional[str] = None

        self.setWindowTitle("P&L Adjustments & Brokerage Manager")
        self.resize(920, 640)
        self.setMinimumSize(850, 560)

        self._init_ui()
        self._load_accounts()
        self._load_ledger()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # Header Title
        title_layout = QHBoxLayout()
        lbl_title = QLabel("⚖️ P&L Adjustments & Brokerage Ledger")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()
        main_layout.addLayout(title_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_add = QWidget()
        self.tab_ledger = QWidget()

        self._init_tab_add()
        self._init_tab_ledger()

        self.tabs.addTab(self.tab_add, "➕ Record Adjustment / Brokerage")
        self.tabs.addTab(self.tab_ledger, "📜 Adjustments Ledger & Audit")
        main_layout.addWidget(self.tabs)

        # Bottom Close Button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)
        main_layout.addLayout(bottom_layout)

    def _init_tab_add(self):
        tab_layout = QVBoxLayout(self.tab_add)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; } QWidget#tab_add_container { background: transparent; }")

        container = QWidget()
        container.setObjectName("tab_add_container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Explanatory card
        desc_card = QFrame()
        desc_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px 12px;")
        desc_layout = QVBoxLayout(desc_card)
        lbl_desc = QLabel(
            "<b>Record Stock P&L Adjustments & Brokerage:</b><br>"
            "• <b>Carried Profit / Loss:</b> Bring forward historical realized P&L from old untracked accounts.<br>"
            "• <b>Brokerage & Taxes:</b> Deduct trading fees, STT, and broker charges from realized gains.<br>"
            "• <b>Stock-Linked:</b> Every adjustment is linked to a specific script to update its cost basis and House Money status."
        )
        lbl_desc.setStyleSheet("font-size: 12px; color: #475569; line-height: 1.35;")
        desc_layout.addWidget(lbl_desc)
        layout.addWidget(desc_card)

        # Preset Buttons Bar
        preset_group = QGroupBox("Quick Category Presets")
        preset_group.setStyleSheet("font-weight: 600; color: #334155;")
        preset_layout = QHBoxLayout(preset_group)
        preset_layout.setSpacing(8)

        self.btn_preset_profit = QPushButton("🟢 Carried Profit")
        self.btn_preset_profit.clicked.connect(lambda: self._apply_preset("CARRIED_FORWARD_PROFIT"))
        preset_layout.addWidget(self.btn_preset_profit)

        self.btn_preset_loss = QPushButton("🔴 Carried Loss")
        self.btn_preset_loss.clicked.connect(lambda: self._apply_preset("CARRIED_FORWARD_LOSS"))
        preset_layout.addWidget(self.btn_preset_loss)

        self.btn_preset_brokerage = QPushButton("🔴 Brokerage & Taxes")
        self.btn_preset_brokerage.clicked.connect(lambda: self._apply_preset("BROKERAGE_CHARGES"))
        preset_layout.addWidget(self.btn_preset_brokerage)

        layout.addWidget(preset_group)

        # Form Fields Grid
        grid = QGridLayout()
        grid.setSpacing(12)

        # Account
        grid.addWidget(QLabel("Target Family Account:"), 0, 0)
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        grid.addWidget(self.combo_account, 0, 1)

        # Stock Symbol (Script) - REQUIRED
        grid.addWidget(QLabel("Stock Symbol (Script):"), 1, 0)
        self.txt_symbol = QLineEdit()
        self.txt_symbol.setPlaceholderText("e.g. INFY, RELIANCE, TCS")
        symbols = get_all_symbols(self.db_conn)
        self.completer = QCompleter(symbols, self.txt_symbol)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        popup = self.completer.popup()
        popup.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px; color: #0F172A;"
        )
        self.txt_symbol.setCompleter(self.completer)
        if self.initial_symbol:
            self.txt_symbol.setText(self.initial_symbol)
        grid.addWidget(self.txt_symbol, 1, 1)

        # Category
        grid.addWidget(QLabel("Category:"), 2, 0)
        self.combo_category = QComboBox()
        self.combo_category.setView(QListView())
        self.combo_category.addItem("Carried-Forward Profit ", "CARRIED_FORWARD_PROFIT")
        self.combo_category.addItem("Carried-Forward Loss ", "CARRIED_FORWARD_LOSS")
        self.combo_category.addItem("Brokerage, Taxes & Exchange Fees", "BROKERAGE_CHARGES")
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        grid.addWidget(self.combo_category, 2, 1)

        # Direction (Profit [+] vs Loss [-])
        grid.addWidget(QLabel("Direction:"), 3, 0)
        dir_widget = QWidget()
        dir_layout = QHBoxLayout(dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(14)
        self.radio_profit = QRadioButton("🟢 Profit / Credit (+)")
        self.radio_loss = QRadioButton("🔴 Loss / Expense / Debit (-)")
        self.dir_group = QButtonGroup(self)
        self.dir_group.addButton(self.radio_profit)
        self.dir_group.addButton(self.radio_loss)
        self.radio_profit.setChecked(True)
        dir_layout.addWidget(self.radio_profit)
        dir_layout.addWidget(self.radio_loss)
        dir_layout.addStretch()
        grid.addWidget(dir_widget, 3, 1)

        # Amount (₹)
        grid.addWidget(QLabel("Amount (₹):"), 4, 0)
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("e.g. 50000.00 or 15.93")
        amt_val = QDoubleValidator(0.01, 1_000_000_000.0, 2, self)
        amt_val.setNotation(QDoubleValidator.StandardNotation)
        self.txt_amount.setValidator(amt_val)
        grid.addWidget(self.txt_amount, 4, 1)

        # Date
        grid.addWidget(QLabel("Effective Date:"), 5, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        configure_modern_calendar(self.date_edit.calendarWidget())
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(self.date_edit, 5, 1)

        # Notes
        grid.addWidget(QLabel("Notes:"), 6, 0)
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. FY21-22 Tax PnL, Old Demat transfer, Contract Note charges")
        grid.addWidget(self.txt_notes, 6, 1)

        layout.addLayout(grid)

        # Action Buttons
        act_layout = QHBoxLayout()
        act_layout.setSpacing(10)
        self.btn_save = QPushButton("➕ Save Adjustment")
        set_style_class(self.btn_save, "primary-btn")
        self.btn_save.setMinimumHeight(38)
        self.btn_save.clicked.connect(self._save_adjustment)
        act_layout.addWidget(self.btn_save)

        self.btn_cancel_edit = QPushButton("Cancel Edit")
        self.btn_cancel_edit.setVisible(False)
        self.btn_cancel_edit.clicked.connect(self._reset_form)
        act_layout.addWidget(self.btn_cancel_edit)

        layout.addLayout(act_layout)
        layout.addStretch()

        scroll.setWidget(container)
        tab_layout.addWidget(scroll)

    def _init_tab_ledger(self):
        layout = QVBoxLayout(self.tab_ledger)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Summary Banner Card
        self.summary_card = QFrame()
        self.summary_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px;")
        summary_layout = QHBoxLayout(self.summary_card)
        self.lbl_summary_text = QLabel("Loading summary...")
        self.lbl_summary_text.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        summary_layout.addWidget(self.lbl_summary_text)
        layout.addWidget(self.summary_card)

        # Search bar
        search_layout = QHBoxLayout()
        self.txt_search_ledger = QLineEdit()
        self.txt_search_ledger.setPlaceholderText("🔍 Search by symbol, account, category, notes...")
        self.txt_search_ledger.setClearButtonEnabled(True)
        self.txt_search_ledger.textChanged.connect(self._filter_ledger)
        search_layout.addWidget(self.txt_search_ledger)

        self.btn_autofit_ledger = QPushButton("↔ Auto-Fit")
        self.btn_autofit_ledger.clicked.connect(self._auto_fit_ledger)
        search_layout.addWidget(self.btn_autofit_ledger)
        layout.addLayout(search_layout)

        # Ledger Table
        self.table_ledger = QTableWidget(0, 8)
        self.table_ledger.setHorizontalHeaderLabels([
            "ID", "Account", "Symbol", "Category", "Direction", "Amount (₹)", "Date", "Notes"
        ])
        header = self.table_ledger.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table_ledger.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_ledger.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_ledger.setAlternatingRowColors(True)
        self.table_ledger.verticalHeader().setVisible(False)
        self.table_ledger.cellDoubleClicked.connect(lambda r, c: self._edit_selected_from_ledger())
        layout.addWidget(self.table_ledger)

        # Ledger Action Buttons
        ledger_btns = QHBoxLayout()
        self.btn_edit_ledger = QPushButton("✏️ Edit Selected")
        set_style_class(self.btn_edit_ledger, "primary-btn")
        self.btn_edit_ledger.clicked.connect(self._edit_selected_from_ledger)
        ledger_btns.addWidget(self.btn_edit_ledger)

        self.btn_delete_ledger = QPushButton("🗑️ Delete Selected")
        set_style_class(self.btn_delete_ledger, "danger-btn")
        self.btn_delete_ledger.clicked.connect(self._delete_selected_from_ledger)
        ledger_btns.addWidget(self.btn_delete_ledger)

        ledger_btns.addStretch()
        layout.addLayout(ledger_btns)

    def _load_accounts(self):
        self.combo_account.clear()
        try:
            accounts = get_accounts(self.db_conn)
            for acc in accounts:
                self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])

            if self.default_account_id:
                idx = self.combo_account.findData(self.default_account_id)
                if idx >= 0:
                    self.combo_account.setCurrentIndex(idx)
        except Exception:
            pass

    def _apply_preset(self, category: str):
        idx = self.combo_category.findData(category)
        if idx >= 0:
            self.combo_category.setCurrentIndex(idx)
        self._on_category_changed()

    def _on_category_changed(self):
        cat = self.combo_category.currentData()
        if cat == "CARRIED_FORWARD_PROFIT":
            self.radio_profit.setChecked(True)
        elif cat in ("CARRIED_FORWARD_LOSS", "BROKERAGE_CHARGES"):
            self.radio_loss.setChecked(True)

    def _reset_form(self):
        self.editing_adjustment_id = None
        self.txt_amount.clear()
        self.txt_symbol.clear()
        self.txt_notes.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.btn_save.setText("➕ Save Adjustment")
        self.btn_cancel_edit.setVisible(False)
        self.combo_category.setCurrentIndex(0)
        self._on_category_changed()

    def _save_adjustment(self):
        account_id = self.combo_account.currentData()
        if not account_id:
            QMessageBox.warning(self, "Invalid Input", "Please select a valid account.")
            return

        symbol = self.txt_symbol.text().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Invalid Input", "Please enter a stock symbol (script) to link this adjustment.")
            self.txt_symbol.setFocus()
            return

        amt_str = self.txt_amount.text().strip().replace(",", "")
        if not amt_str:
            QMessageBox.warning(self, "Invalid Input", "Please enter an adjustment amount.")
            self.txt_amount.setFocus()
            return

        try:
            amount = float(amt_str)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Amount must be a positive number greater than 0.")
            self.txt_amount.setFocus()
            return

        category = self.combo_category.currentData()
        direction = "PROFIT" if self.radio_profit.isChecked() else "LOSS"
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        notes = self.txt_notes.text().strip() or None

        try:
            if self.editing_adjustment_id:
                success = update_pnl_adjustment(
                    conn=self.db_conn,
                    adjustment_id=self.editing_adjustment_id,
                    account_id=account_id,
                    amount=amount,
                    adjustment_date=date_str,
                    category=category,
                    direction=direction,
                    symbol=symbol,
                    notes=notes,
                )
                if not success:
                    QMessageBox.critical(self, "Error", "Could not update adjustment.")
                    return
                msg = "Adjustment updated successfully."
            else:
                insert_pnl_adjustment(
                    conn=self.db_conn,
                    account_id=account_id,
                    amount=amount,
                    adjustment_date=date_str,
                    category=category,
                    direction=direction,
                    symbol=symbol,
                    notes=notes,
                )
                msg = "Adjustment recorded successfully."

            self._reset_form()
            self._load_ledger()
            self.adjustments_changed.emit()
            QMessageBox.information(self, "Success", msg)
            self.tabs.setCurrentIndex(1)  # View ledger
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save adjustment:\n{e}")

    def _load_ledger(self):
        self.table_ledger.setSortingEnabled(False)
        try:
            adjs = get_pnl_adjustments(self.db_conn)
            self.table_ledger.setRowCount(len(adjs))

            for r, a in enumerate(adjs):
                # ID
                it_id = NumericTableWidgetItem(str(a["adjustment_id"]))
                it_id.setData(Qt.UserRole, a["adjustment_id"])
                self.table_ledger.setItem(r, 0, it_id)

                # Account
                it_acc = NumericTableWidgetItem(str(a["user_name"]))
                it_acc.setData(Qt.UserRole, a["account_id"])
                self.table_ledger.setItem(r, 1, it_acc)

                # Symbol
                sym_str = str(a["canonical_symbol"] or a["symbol"] or "— (Account-Wide)")
                if a.get("is_mapped") and a.get("original_symbol") != a.get("canonical_symbol"):
                    sym_display = f"{a['original_symbol']} ➔ {a['canonical_symbol']}"
                else:
                    sym_display = sym_str
                it_sym = NumericTableWidgetItem(sym_display)
                it_sym.setData(Qt.UserRole, a.get("canonical_symbol") or "")
                it_sym.setData(Qt.UserRole + 1, a.get("original_symbol") or "")
                self.table_ledger.setItem(r, 2, it_sym)

                # Category
                cat_display = str(a["category"]).replace("_", " ").title()
                it_cat = NumericTableWidgetItem(cat_display)
                self.table_ledger.setItem(r, 3, it_cat)

                # Direction
                is_profit = a["direction"] == "PROFIT"
                dir_display = "+ PROFIT" if is_profit else "- LOSS / CHG"
                it_dir = NumericTableWidgetItem(dir_display)
                it_dir.setTextAlignment(Qt.AlignCenter)
                if is_profit:
                    it_dir.setForeground(QColor("#047857"))
                else:
                    it_dir.setForeground(QColor("#B91C1C"))
                font_bold = it_dir.font()
                font_bold.setBold(True)
                it_dir.setFont(font_bold)
                self.table_ledger.setItem(r, 4, it_dir)

                # Amount
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
                self.table_ledger.setItem(r, 5, it_amt)

                # Date
                date_str = str(a["adjustment_date"])[:10]
                it_date = NumericTableWidgetItem(date_str)
                it_date.setTextAlignment(Qt.AlignCenter)
                self.table_ledger.setItem(r, 6, it_date)

                # Notes
                it_notes = NumericTableWidgetItem(str(a.get("notes") or ""))
                self.table_ledger.setItem(r, 7, it_notes)

            # Update Summary Bar
            summary = get_adjustments_summary(self.db_conn)
            net_amt = summary["net_adjustments"]
            net_color = "#047857" if net_amt >= 0 else "#B91C1C"
            net_sign = "+" if net_amt >= 0 else "-"
            self.lbl_summary_text.setText(
                f"Total Entries: {summary['adjustments_count']}  |  "
                f"🟢 Carried Profit: +₹{summary['total_carried_profit']:,.2f}  |  "
                f"🔴 Charges / Brokerage: -₹{summary['total_brokerage']:,.2f}  |  "
                f"<b>Net P&L Adjustment: <span style='color: {net_color};'>{net_sign}₹{abs(net_amt):,.2f}</span></b>"
            )
        except Exception as e:
            self.lbl_summary_text.setText(f"Error loading summary: {e}")

        self.table_ledger.setSortingEnabled(True)
        self._auto_fit_ledger()
        self._filter_ledger()

    def _auto_fit_ledger(self):
        self.table_ledger.resizeColumnsToContents()
        min_widths = [110, 120, 110, 150, 100, 110, 110, 220]
        for col, min_w in enumerate(min_widths):
            if col < self.table_ledger.columnCount():
                if self.table_ledger.columnWidth(col) < min_w:
                    self.table_ledger.setColumnWidth(col, min_w)
        self.table_ledger.horizontalHeader().setStretchLastSection(True)

    def _filter_ledger(self):
        query = self.txt_search_ledger.text().strip().lower()
        total_rows = self.table_ledger.rowCount()
        for r in range(total_rows):
            row_text = " ".join(
                self.table_ledger.item(r, c).text() for c in range(self.table_ledger.columnCount()) if self.table_ledger.item(r, c)
            ).lower()
            match = (query in row_text) if query else True
            self.table_ledger.setRowHidden(r, not match)

    def _edit_selected_from_ledger(self):
        selected_rows = self.table_ledger.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Row", "Please select an adjustment row to edit.")
            return

        row_idx = selected_rows[0].row()
        adj_id = self.table_ledger.item(row_idx, 0).text()

        adj = get_pnl_adjustment(self.db_conn, adj_id)
        if not adj:
            QMessageBox.critical(self, "Error", f"Adjustment '{adj_id}' not found.")
            return

        self.editing_adjustment_id = adj_id
        self.btn_save.setText("💾 Update Adjustment")
        self.btn_cancel_edit.setVisible(True)

        # Populate form
        idx = self.combo_account.findData(adj["account_id"])
        if idx >= 0:
            self.combo_account.setCurrentIndex(idx)

        idx_cat = self.combo_category.findData(adj["category"])
        if idx_cat >= 0:
            self.combo_category.setCurrentIndex(idx_cat)

        if adj["direction"] == "PROFIT":
            self.radio_profit.setChecked(True)
        else:
            self.radio_loss.setChecked(True)

        self.txt_amount.setText(str(adj["amount"]))
        self.txt_symbol.setText(adj["symbol"] or "")
        d = QDate.fromString(str(adj["adjustment_date"])[:10], "yyyy-MM-dd")
        if d.isValid():
            self.date_edit.setDate(d)
        self.txt_notes.setText(adj.get("notes") or "")

        self.tabs.setCurrentIndex(0)

    def _delete_selected_from_ledger(self):
        selected_rows = self.table_ledger.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Row", "Please select an adjustment row to delete.")
            return

        row_idx = selected_rows[0].row()
        adj_id = self.table_ledger.item(row_idx, 0).text()
        cat = self.table_ledger.item(row_idx, 3).text()
        amt = self.table_ledger.item(row_idx, 5).text()

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete adjustment '{adj_id}'?\n\n"
            f"Category: {cat}\n"
            f"Amount: {amt}\n\n"
            "This will update your portfolio cost basis and ledger immediately.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success = delete_pnl_adjustment(self.db_conn, adj_id)
            if success:
                self._load_ledger()
                self.adjustments_changed.emit()
                QMessageBox.information(self, "Deleted", "Adjustment deleted successfully.")
            else:
                QMessageBox.critical(self, "Error", "Could not delete adjustment.")
