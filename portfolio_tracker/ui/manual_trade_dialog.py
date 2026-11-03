"""Dialog for manually adding transactions to fix irregularities, off-market transfers, or missing trades."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, Qt, Signal
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

from portfolio_tracker.db import get_accounts, get_all_symbols, insert_manual_transaction
from portfolio_tracker.ui.styles import configure_modern_calendar, set_style_class


class ManualTradeDialog(QDialog):
    """Senior-friendly modal dialog for recording manual trade adjustments."""

    trade_added = Signal()

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        default_account_id: str = None,
        initial_symbol: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.db_conn = db_conn
        self.default_account_id = default_account_id
        self.initial_symbol = (initial_symbol or "").strip()
        self.setWindowTitle("Record Manual Trade Adjustment")
        self.setMinimumSize(480, 400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Add Manual Transaction")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        desc = QLabel(
            "Use this form to input missing buy or sell trades, off-market transfers, "
            "or corporate adjustments to keep your cost basis accurate."
        )
        desc.setStyleSheet("color: #64748B; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)

        # 1. Target Account
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])

        if self.default_account_id:
            idx = self.combo_account.findData(self.default_account_id)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)

        form.addRow("Target Account:", self.combo_account)

        # 2. Symbol with Autocomplete Recommendations
        self.txt_symbol = QLineEdit()
        self.txt_symbol.setPlaceholderText("e.g. INFY, RELIANCE, TCS")

        # Load known symbols for instant suggestion dropdown
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
        form.addRow("Stock Symbol:", self.txt_symbol)

        # 3. Transaction Type
        self.combo_type = QComboBox()
        self.combo_type.setView(QListView())
        self.combo_type.addItem("BUY (Purchase / Acquisition)", "BUY")
        self.combo_type.addItem("SELL (Sale / Disposal)", "SELL")
        form.addRow("Transaction Type:", self.combo_type)

        # 4. Quantity (Pure number input, no up/down stepper arrows)
        self.txt_qty = QLineEdit()
        self.txt_qty.setPlaceholderText("e.g. 100")
        self.txt_qty.setValidator(QIntValidator(1, 10_000_000, self))
        form.addRow("Quantity (Shares):", self.txt_qty)

        # 5. Price (Pure number input with decimal validation, no up/down stepper arrows)
        self.txt_price = QLineEdit()
        self.txt_price.setPlaceholderText("e.g. 100.00 (or 0 for bonus)")
        price_val = QDoubleValidator(0.00, 10_000_000.0, 2, self)
        price_val.setNotation(QDoubleValidator.StandardNotation)
        self.txt_price.setValidator(price_val)
        form.addRow("Execution Price (₹):", self.txt_price)

        # 6. Trade Date (Date only picker, time is not relevant)
        self.date_picker = QDateEdit()
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        configure_modern_calendar(self.date_picker.calendarWidget())
        self.date_picker.setDisplayFormat("dd-MM-yyyy")
        form.addRow("Trade Date:", self.date_picker)

        # 7. Notes with Default Options (IPO, Bonus/Split) and Free Text
        notes_box = QVBoxLayout()
        notes_box.setSpacing(6)

        self.combo_notes = QComboBox()
        self.combo_notes.setEditable(True)
        self.combo_notes.setView(QListView())
        self.combo_notes.addItem("")
        self.combo_notes.addItem("IPO")
        self.combo_notes.addItem("Bonus/Split")
        self.combo_notes.lineEdit().setPlaceholderText("Select default (IPO, Bonus/Split) or type custom note...")
        self.txt_notes = self.combo_notes.lineEdit()
        notes_box.addWidget(self.combo_notes)

        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        lbl_preset = QLabel("Presets:")
        lbl_preset.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        preset_layout.addWidget(lbl_preset)

        self.btn_preset_ipo = QPushButton("IPO")
        self.btn_preset_ipo.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 4px; "
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; color: #1E293B; min-height: 20px;"
        )
        self.btn_preset_ipo.clicked.connect(lambda: self.combo_notes.setCurrentText("IPO"))
        preset_layout.addWidget(self.btn_preset_ipo)

        def _apply_bonus_preset():
            self.combo_notes.setCurrentText("Bonus/Split")
            self.txt_price.setText("0.00")
            idx = self.combo_type.findData("BUY")
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)

        self.btn_preset_bonus = QPushButton("Bonus/Split")
        self.btn_preset_bonus.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 4px; "
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; color: #1E293B; min-height: 20px;"
        )
        self.btn_preset_bonus.clicked.connect(_apply_bonus_preset)
        preset_layout.addWidget(self.btn_preset_bonus)
        preset_layout.addStretch()
        notes_box.addLayout(preset_layout)

        form.addRow("Notes (Optional):", notes_box)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Transaction")
        set_style_class(self.btn_save, "primary-btn")
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    # Backward compatibility properties for test suite and external callers
    @property
    def spin_qty(self):
        class _QtyWrapper:
            def __init__(self, target: QLineEdit):
                self._t = target
            def value(self) -> int:
                try:
                    return int(self._t.text().strip() or "0")
                except ValueError:
                    return 0
            def setValue(self, v: int) -> None:
                self._t.setText(str(v))
        return _QtyWrapper(self.txt_qty)

    @property
    def spin_price(self):
        class _PriceWrapper:
            def __init__(self, target: QLineEdit):
                self._t = target
            def value(self) -> float:
                try:
                    return float(self._t.text().strip() or "0.0")
                except ValueError:
                    return 0.0
            def setValue(self, v: float) -> None:
                self._t.setText(f"{v:.2f}")
        return _PriceWrapper(self.txt_price)

    @property
    def dt_picker(self):
        class _DtWrapper:
            def __init__(self, target: QDateEdit):
                self._t = target
            def date(self) -> QDate:
                return self._t.date()
            def setDate(self, d: QDate) -> None:
                self._t.setDate(d)
            def dateTime(self) -> QDateTime:
                return self._t.dateTime()
            def calendarWidget(self):
                return self._t.calendarWidget()
        return _DtWrapper(self.date_picker)

    def _on_save(self):
        account_id = self.combo_account.currentData()
        symbol = self.txt_symbol.text().strip().upper()
        tx_type = self.combo_type.currentData()

        if not symbol:
            QMessageBox.warning(self, "Missing Symbol", "Please enter a valid stock symbol.")
            self.txt_symbol.setFocus()
            return

        # Number type validation for Quantity
        try:
            qty_str = self.txt_qty.text().strip()
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Invalid Quantity", "Please enter a valid positive integer quantity (e.g. 100).")
            self.txt_qty.setFocus()
            return

        # Number type validation for Price
        try:
            price_str = self.txt_price.text().strip().replace("₹", "").strip()
            price = float(price_str)
            if price < 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Invalid Price", "Please enter a non-negative execution price (₹0.00 for bonus shares or e.g. 150.50).")
            self.txt_price.setFocus()
            return

        trade_date_str = f"{self.date_picker.date().toString('yyyy-MM-dd')} 00:00:00"
        notes = self.combo_notes.currentText().strip() or None

        try:
            trade_id = insert_manual_transaction(
                conn=self.db_conn,
                account_id=account_id,
                symbol=symbol,
                transaction_type=tx_type,
                quantity=qty,
                price=price,
                trade_date=trade_date_str,
                notes=notes,
            )
            self.trade_added.emit()
            QMessageBox.information(
                self,
                "Trade Recorded",
                f"Successfully recorded manual {tx_type} of {qty} {symbol} @ ₹{price:,.2f}.\nTrade ID: {trade_id}",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to record manual trade:\n{e}")

