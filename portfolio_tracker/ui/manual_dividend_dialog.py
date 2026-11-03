"""Modal dialog for manually recording or editing dividend transactions with symbol autocomplete."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDate, QStringListModel, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from portfolio_tracker.db import (
    get_accounts,
    get_all_symbols,
    get_dividend,
    insert_dividend,
    update_dividend,
)
from portfolio_tracker.ui.styles import configure_modern_calendar, set_style_class


class ManualDividendDialog(QDialog):
    """Dialog for recording off-market or manual dividend credits with symbol autocomplete."""

    dividend_saved = Signal()

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        default_account_id: Optional[str] = None,
        editing_dividend_id: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db_conn = db_conn
        self.default_account_id = default_account_id
        self.editing_dividend_id = editing_dividend_id

        title = "Edit Dividend Record" if editing_dividend_id else "Record Manual Dividend"
        self.setWindowTitle(title)
        self.setFixedWidth(460)
        self._init_ui()
        self._load_symbols_completer()

        if self.editing_dividend_id:
            self._load_existing_dividend()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header Title
        title_text = "✏️ Edit Dividend" if self.editing_dividend_id else "➕ Record Manual Dividend"
        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        main_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Record dividend income received directly in your bank account or missing from imports."
        )
        lbl_desc.setStyleSheet("color: #64748B; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        main_layout.addWidget(lbl_desc)

        form = QFormLayout()
        form.setSpacing(12)

        # 1. Target Account
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            label = f"{acc['user_name']} ({acc['account_id']})"
            self.combo_account.addItem(label, acc["account_id"])

        if self.default_account_id:
            idx = self.combo_account.findData(self.default_account_id)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)
        form.addRow("Family Account:", self.combo_account)

        # 2. Stock Symbol with Autocomplete
        self.txt_symbol = QLineEdit()
        self.txt_symbol.setPlaceholderText("e.g. INFY, RELIANCE, TCS")
        form.addRow("Stock Symbol:", self.txt_symbol)

        # 3. Dividend Date (dd-MM-yyyy format)
        self.date_picker = QDateEdit()
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        configure_modern_calendar(self.date_picker.calendarWidget())
        self.date_picker.setDisplayFormat("dd-MM-yyyy")
        form.addRow("Dividend Date:", self.date_picker)

        # 4. Shares Held (Quantity)
        self.txt_quantity = QLineEdit()
        self.txt_quantity.setPlaceholderText("e.g. 100")
        qty_val = QIntValidator(0, 10000000, self)
        self.txt_quantity.setValidator(qty_val)
        self.txt_quantity.textChanged.connect(self._auto_calc_total)
        form.addRow("Shares Held:", self.txt_quantity)

        # 5. Dividend Per Share (DPS)
        self.txt_dps = QLineEdit()
        self.txt_dps.setPlaceholderText("e.g. 15.50")
        dps_val = QDoubleValidator(0.0, 100000.0, 4, self)
        dps_val.setNotation(QDoubleValidator.StandardNotation)
        self.txt_dps.setValidator(dps_val)
        self.txt_dps.textChanged.connect(self._auto_calc_total)
        form.addRow("Dividend / Share (₹):", self.txt_dps)

        # 6. Total Amount (Read-only, auto-calculated from Shares × DPS)
        self.txt_amount = QLineEdit()
        self.txt_amount.setReadOnly(True)
        self.txt_amount.setFocusPolicy(Qt.NoFocus)
        self.txt_amount.setPlaceholderText("0.00 (auto-calculated: Shares × DPS)")
        self.txt_amount.setStyleSheet(
            "QLineEdit[readOnly=\"true\"] { background-color: #F1F5F9; color: #0F172A; font-weight: 700; border: 1px solid #CBD5E1; }"
        )
        form.addRow("Total Dividend (₹):", self.txt_amount)

        # 7. Remarks / Notes
        self.txt_remarks = QLineEdit()
        self.txt_remarks.setPlaceholderText("Optional notes or banking narration")
        form.addRow("Remarks / Notes:", self.txt_remarks)

        main_layout.addLayout(form)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        save_label = "Update Dividend" if self.editing_dividend_id else "Save Dividend"
        self.btn_save = QPushButton(save_label)
        set_style_class(self.btn_save, "primary-btn")
        self.btn_save.clicked.connect(self._save_dividend)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    def _load_symbols_completer(self):
        """Bind system symbols to autocomplete popup."""
        symbols = get_all_symbols(self.db_conn)
        completer = QCompleter(symbols, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer_popup = QListView()
        completer.setPopup(completer_popup)
        self.txt_symbol.setCompleter(completer)

    def _auto_calc_total(self):
        """Auto-calculate total amount when quantity and DPS are filled."""
        try:
            qty_text = self.txt_quantity.text().strip()
            dps_text = self.txt_dps.text().strip()
            if qty_text and dps_text:
                qty = int(qty_text)
                dps = float(dps_text)
                if qty > 0 and dps > 0:
                    calc_amt = round(qty * dps, 2)
                    self.txt_amount.setText(f"{calc_amt:.2f}")
                    return
            self.txt_amount.setText("0.00")
        except Exception:
            self.txt_amount.setText("0.00")

    def _load_existing_dividend(self):
        """Populate form with existing dividend details if editing."""
        if not self.editing_dividend_id:
            return
        row = get_dividend(self.db_conn, self.editing_dividend_id)
        if not row:
            QMessageBox.critical(self, "Error", "Dividend record not found.")
            self.reject()
            return

        idx = self.combo_account.findData(row["account_id"])
        if idx >= 0:
            self.combo_account.setCurrentIndex(idx)

        self.txt_symbol.setText(row["symbol"])
        if row["quantity"] > 0:
            self.txt_quantity.setText(str(row["quantity"]))
        if row["dividend_per_share"] > 0:
            self.txt_dps.setText(str(row["dividend_per_share"]))
        elif row["quantity"] > 0 and row["amount"] > 0:
            self.txt_dps.setText(str(round(row["amount"] / row["quantity"], 4)))

        self._auto_calc_total()
        if not self.txt_amount.text() or self.txt_amount.text() == "0.00":
            self.txt_amount.setText(str(row["amount"]))

        if row["remarks"]:
            self.txt_remarks.setText(row["remarks"])

        raw_date = str(row["dividend_date"]).strip()[:10]
        try:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
            self.date_picker.setDate(QDate(dt.year, dt.month, dt.day))
        except Exception:
            pass

    def _save_dividend(self):
        acc_id = self.combo_account.currentData()
        sym = self.txt_symbol.text().strip().upper().rstrip("#*").strip()

        if not acc_id:
            QMessageBox.warning(self, "Validation Error", "Please select an account.")
            return
        if not sym:
            QMessageBox.warning(self, "Validation Error", "Stock symbol cannot be empty.")
            return

        qty_text = self.txt_quantity.text().strip()
        dps_text = self.txt_dps.text().strip()

        if not qty_text:
            QMessageBox.warning(self, "Validation Error", "Shares held (Quantity) is required.")
            return
        if not dps_text:
            QMessageBox.warning(self, "Validation Error", "Dividend per share (DPS) is required.")
            return

        try:
            qty = int(qty_text)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Shares held must be an integer greater than 0.")
            return

        try:
            dps = float(dps_text)
            if dps <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Dividend per share must be greater than 0.")
            return

        amount = round(qty * dps, 2)
        if amount <= 0:
            QMessageBox.warning(self, "Validation Error", "Total calculated dividend must be greater than 0.")
            return

        self.txt_amount.setText(f"{amount:.2f}")

        date_str = f"{self.date_picker.date().toString('yyyy-MM-dd')} 12:00:00"
        remarks = self.txt_remarks.text().strip() or None

        try:
            if self.editing_dividend_id:
                update_dividend(
                    conn=self.db_conn,
                    dividend_id=self.editing_dividend_id,
                    account_id=acc_id,
                    symbol=sym,
                    dividend_date=date_str,
                    amount=amount,
                    quantity=qty,
                    dividend_per_share=dps,
                    remarks=remarks,
                )
            else:
                insert_dividend(
                    conn=self.db_conn,
                    account_id=acc_id,
                    symbol=sym,
                    dividend_date=date_str,
                    amount=amount,
                    quantity=qty,
                    dividend_per_share=dps,
                    remarks=remarks,
                )
            self.dividend_saved.emit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Dividend", str(e))

