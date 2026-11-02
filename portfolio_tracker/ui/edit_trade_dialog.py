"""Dialog for editing transaction details with mandatory reason notes and a confirmation review tab."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import (
    get_accounts,
    get_all_symbols,
    get_transaction,
    update_transaction,
)
from portfolio_tracker.ui.styles import (
    NumericTableWidgetItem,
    configure_modern_calendar,
    set_style_class,
)


class EditTradeDialog(QDialog):
    """Senior-friendly modal dialog for modifying existing trades with a confirmation tab."""

    trade_updated = Signal(str)

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        trade_id: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db_conn = db_conn
        self.trade_id = trade_id
        self.original_trade: Optional[Dict[str, Any]] = get_transaction(db_conn, trade_id)

        if not self.original_trade:
            raise ValueError(f"Transaction '{trade_id}' not found in database.")

        self.setWindowTitle(f"Edit Trade Details - {self.original_trade['symbol']}")
        self.setMinimumSize(640, 560)
        self.resize(680, 600)

        self._init_ui()
        self._populate_original_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header Title and Trade ID pill
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(2)

        title = QLabel("Edit Transaction Details")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        header_left.addWidget(title)

        desc = QLabel("Adjust trade details for corporate actions like stock splits, bonus issues, or typo fixes.")
        desc.setStyleSheet("color: #64748B; font-size: 13px;")
        header_left.addWidget(desc)
        header_layout.addLayout(header_left)

        header_layout.addStretch()

        # Trade ID chip
        chip = QLabel(f"Trade ID: {self.trade_id}")
        chip.setStyleSheet(
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 6px; "
            "color: #475569; font-size: 11px; font-family: monospace; padding: 4px 10px;"
        )
        header_layout.addWidget(chip, alignment=Qt.AlignTop)

        main_layout.addLayout(header_layout)

        # Tab Widget: 1. Edit Details, 2. Confirmation
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 8px;
            }
            QTabBar::tab {
                font-weight: 600;
                font-size: 13px;
                padding: 8px 20px;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background-color: #F1F5F9;
                color: #64748B;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #0F172A;
                border-bottom: 2px solid #2563EB;
            }
        """)

        # ----------------------------------------------------
        # TAB 1: Edit Details Form
        # ----------------------------------------------------
        self.tab_edit = QWidget()
        tab_edit_layout = QVBoxLayout(self.tab_edit)
        tab_edit_layout.setContentsMargins(18, 18, 18, 18)
        tab_edit_layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 1. Target Account
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])
        form.addRow("Target Account:", self.combo_account)

        # 2. Stock Symbol
        self.txt_symbol = QLineEdit()
        self.txt_symbol.setPlaceholderText("e.g. INFY, RELIANCE, TCS")
        symbols = get_all_symbols(self.db_conn)
        self.completer = QCompleter(symbols, self.txt_symbol)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.txt_symbol.setCompleter(self.completer)
        form.addRow("Stock Symbol:", self.txt_symbol)

        # 3. Transaction Type
        self.combo_type = QComboBox()
        self.combo_type.setView(QListView())
        self.combo_type.addItem("BUY (Purchase / Acquisition)", "BUY")
        self.combo_type.addItem("SELL (Sale / Disposal)", "SELL")
        form.addRow("Transaction Type:", self.combo_type)

        # 4. Quantity (Shares)
        self.txt_qty = QLineEdit()
        self.txt_qty.setPlaceholderText("e.g. 100")
        self.txt_qty.setValidator(QIntValidator(1, 100_000_000, self))
        form.addRow("Quantity (Shares):", self.txt_qty)

        # 5. Price (₹)
        self.txt_price = QLineEdit()
        self.txt_price.setPlaceholderText("e.g. 150.50 (or 0.00 for bonus)")
        price_val = QDoubleValidator(0.00, 100_000_000.0, 2, self)
        price_val.setNotation(QDoubleValidator.StandardNotation)
        self.txt_price.setValidator(price_val)
        form.addRow("Price per Share (₹):", self.txt_price)

        # 6. Trade Date
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        configure_modern_calendar(self.date_picker.calendarWidget())
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Trade Date:", self.date_picker)

        # 7. Reason / Note for Change (Required)
        notes_box = QVBoxLayout()
        notes_box.setSpacing(6)

        self.combo_notes = QComboBox()
        self.combo_notes.setEditable(True)
        self.combo_notes.setView(QListView())
        self.combo_notes.addItem("Stock Split adjustment")
        self.combo_notes.addItem("Bonus Issue adjustment")
        self.combo_notes.addItem("Price / Quantity correction")
        self.combo_notes.addItem("Off-market Demerger adjustment")
        self.txt_notes = self.combo_notes.lineEdit()
        self.txt_notes.setPlaceholderText("Required: specify reason (e.g. 1:2 split, bonus, correction)...")
        notes_box.addWidget(self.combo_notes)

        # Preset Quick Buttons
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        lbl_presets = QLabel("Presets:")
        lbl_presets.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        preset_layout.addWidget(lbl_presets)

        btn_split = QPushButton("⚡ Stock Split")
        btn_split.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 4px; background-color: #F1F5F9; border: 1px solid #CBD5E1;")
        btn_split.clicked.connect(lambda: self.combo_notes.setEditText("Stock Split adjustment"))
        preset_layout.addWidget(btn_split)

        def _apply_bonus():
            self.combo_notes.setEditText("Bonus Issue adjustment")
            self.txt_price.setText("0.00")
            idx = self.combo_type.findData("BUY")
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)

        btn_bonus = QPushButton("🎁 Bonus Issue")
        btn_bonus.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 4px; background-color: #F1F5F9; border: 1px solid #CBD5E1;")
        btn_bonus.clicked.connect(_apply_bonus)
        preset_layout.addWidget(btn_bonus)

        btn_correction = QPushButton("🏷️ Correction")
        btn_correction.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 4px; background-color: #F1F5F9; border: 1px solid #CBD5E1;")
        btn_correction.clicked.connect(lambda: self.combo_notes.setEditText("Price/Quantity correction"))
        preset_layout.addWidget(btn_correction)

        preset_layout.addStretch()
        notes_box.addLayout(preset_layout)

        form.addRow("Reason for Change *:", notes_box)

        tab_edit_layout.addLayout(form)
        tab_edit_layout.addStretch()

        # Tab 1 bottom action buttons
        tab_edit_btn_layout = QHBoxLayout()
        btn_cancel_edit = QPushButton("Cancel")
        btn_cancel_edit.clicked.connect(self.reject)
        tab_edit_btn_layout.addWidget(btn_cancel_edit)

        tab_edit_btn_layout.addStretch()

        self.btn_next = QPushButton("Next: Review & Confirm →")
        set_style_class(self.btn_next, "primary-btn")
        self.btn_next.setMinimumWidth(180)
        self.btn_next.clicked.connect(self._go_to_confirmation)
        tab_edit_btn_layout.addWidget(self.btn_next)

        tab_edit_layout.addLayout(tab_edit_btn_layout)
        self.tabs.addTab(self.tab_edit, "1. Edit Details")

        # ----------------------------------------------------
        # TAB 2: Confirmation & Comparison Review
        # ----------------------------------------------------
        self.tab_confirm = QWidget()
        tab_confirm_layout = QVBoxLayout(self.tab_confirm)
        tab_confirm_layout.setContentsMargins(18, 18, 18, 18)
        tab_confirm_layout.setSpacing(14)

        # Warning / Impact Notice Banner
        notice_frame = QFrame()
        notice_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFBEB;
                border: 1px solid #FCD34D;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        notice_layout = QHBoxLayout(notice_frame)
        notice_layout.setContentsMargins(10, 6, 10, 6)
        notice_icon = QLabel("⚠️")
        notice_icon.setStyleSheet("font-size: 20px;")
        notice_layout.addWidget(notice_icon)

        notice_text = QLabel(
            "<b>Please review your changes carefully.</b><br>"
            "Saving this update will immediately recalculate the Adjusted Cost Basis (ACB), "
            "Actual Exposure, Booked P&L, and Net Exposure for this position."
        )
        notice_text.setStyleSheet("color: #92400E; font-size: 12px; line-height: 1.4;")
        notice_text.setWordWrap(True)
        notice_layout.addWidget(notice_text, 1)
        tab_confirm_layout.addWidget(notice_frame)

        # Before vs After Comparison Table
        lbl_compare = QLabel("Before vs After Comparison:")
        lbl_compare.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 13px;")
        tab_confirm_layout.addWidget(lbl_compare)

        self.table_compare = QTableWidget(0, 4)
        self.table_compare.setHorizontalHeaderLabels([
            "Field", "Original (Before)", "Updated (After)", "Change Status"
        ])
        c_hdr = self.table_compare.horizontalHeader()
        c_hdr.setSectionResizeMode(QHeaderView.Interactive)
        c_hdr.setStretchLastSection(True)
        self.table_compare.setColumnWidth(0, 150)
        self.table_compare.setColumnWidth(1, 160)
        self.table_compare.setColumnWidth(2, 160)
        self.table_compare.setColumnWidth(3, 130)

        self.table_compare.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_compare.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_compare.setAlternatingRowColors(True)
        self.table_compare.verticalHeader().setVisible(False)
        self.table_compare.verticalHeader().setDefaultSectionSize(32)
        tab_confirm_layout.addWidget(self.table_compare)

        # Reason note callout
        self.lbl_confirm_reason = QLabel()
        self.lbl_confirm_reason.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; "
            "padding: 8px 12px; color: #1E293B; font-size: 13px;"
        )
        self.lbl_confirm_reason.setWordWrap(True)
        tab_confirm_layout.addWidget(self.lbl_confirm_reason)

        tab_confirm_layout.addStretch()

        # Tab 2 action buttons: Back to Edit vs Save
        tab_confirm_btn_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Back to Edit")
        self.btn_back.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        tab_confirm_btn_layout.addWidget(self.btn_back)

        tab_confirm_btn_layout.addStretch()

        self.btn_save = QPushButton("💾 Confirm & Save Changes")
        set_style_class(self.btn_save, "success-btn")
        self.btn_save.setMinimumWidth(200)
        self.btn_save.clicked.connect(self._save_changes)
        tab_confirm_btn_layout.addWidget(self.btn_save)

        tab_confirm_layout.addLayout(tab_confirm_btn_layout)
        self.tabs.addTab(self.tab_confirm, "2. Confirmation")

        # Intercept manual tab switching to ensure validation
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

    def _populate_original_data(self):
        """Populate edit form fields with current database transaction values."""
        t = self.original_trade
        if not t:
            return

        # 1. Account
        idx = self.combo_account.findData(t["account_id"])
        if idx >= 0:
            self.combo_account.setCurrentIndex(idx)

        # 2. Symbol
        self.txt_symbol.setText(t["symbol"])

        # 3. Type
        tx_type = str(t["transaction_type"]).upper()
        idx_type = self.combo_type.findData(tx_type)
        if idx_type >= 0:
            self.combo_type.setCurrentIndex(idx_type)

        # 4. Quantity
        self.txt_qty.setText(str(t["quantity"]))

        # 5. Price
        self.txt_price.setText(f"{float(t['price']):.2f}")

        # 6. Trade Date
        date_raw = str(t["trade_date"])[:10]
        qdate = QDate.fromString(date_raw, "yyyy-MM-dd")
        if qdate.isValid():
            self.date_picker.setDate(qdate)

        # 7. Notes
        orig_notes = t.get("notes") or ""
        self.combo_notes.setEditText(orig_notes)

    def _validate_inputs(self) -> Optional[str]:
        """Validate all form inputs, returning an error message if invalid."""
        sym = self.txt_symbol.text().strip().upper()
        if not sym:
            return "Please enter a valid stock symbol."

        # Validate Quantity
        try:
            qty = int(self.txt_qty.text().strip())
            if qty <= 0:
                raise ValueError()
        except Exception:
            return "Please enter a valid positive integer quantity (e.g. 100)."

        # Validate Price
        try:
            price = float(self.txt_price.text().strip().replace("₹", "").replace(",", ""))
            if price < 0:
                raise ValueError()
        except Exception:
            return "Please enter a non-negative execution price (₹0.00 for bonus shares or e.g. 150.50)."

        # Validate Reason/Note (Required)
        note = self.combo_notes.currentText().strip()
        if not note:
            return "Please provide a note or reason for modifying this transaction (e.g. Stock Split, Bonus Issue, or Trade Correction)."

        return None

    def _go_to_confirmation(self):
        """Validate edit form and navigate to the confirmation comparison tab."""
        err = self._validate_inputs()
        if err:
            QMessageBox.warning(self, "Incomplete Details", err)
            if "reason" in err.lower() or "note" in err.lower():
                self.combo_notes.setFocus()
            elif "symbol" in err.lower():
                self.txt_symbol.setFocus()
            elif "quantity" in err.lower():
                self.txt_qty.setFocus()
            elif "price" in err.lower():
                self.txt_price.setFocus()
            return

        self._build_comparison_table()
        self.tabs.setCurrentIndex(1)

    def _on_tab_changed(self, index: int):
        """Prevent user from switching directly to confirmation tab if inputs are invalid."""
        if index == 1:
            err = self._validate_inputs()
            if err:
                QMessageBox.warning(self, "Incomplete Details", err)
                # Switch back to Edit tab
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(0)
                self.tabs.blockSignals(False)
                return
            self._build_comparison_table()

    def _build_comparison_table(self):
        """Construct the Before vs After comparison grid highlighting differences."""
        orig = self.original_trade
        new_acc_id = self.combo_account.currentData()
        new_acc_text = self.combo_account.currentText()
        new_sym = self.txt_symbol.text().strip().upper()
        new_type = self.combo_type.currentData()
        new_qty = int(self.txt_qty.text().strip())
        new_price = float(self.txt_price.text().strip().replace("₹", "").replace(",", ""))
        new_date = self.date_picker.date().toString("yyyy-MM-dd")
        new_note = self.combo_notes.currentText().strip()

        orig_acc_id = orig["account_id"]
        orig_acc_text = f"{orig.get('user_name', orig_acc_id)} ({orig_acc_id})"
        orig_sym = orig["symbol"]
        orig_type = orig["transaction_type"]
        orig_qty = int(orig["quantity"])
        orig_price = float(orig["price"])
        orig_date = str(orig["trade_date"])[:10]
        orig_note = orig.get("notes") or "-"

        orig_total = orig_qty * orig_price
        new_total = new_qty * new_price

        rows_data = [
            ("Stock Symbol", orig_sym, new_sym, orig_sym != new_sym),
            ("Target Account", orig_acc_text, new_acc_text, orig_acc_id != new_acc_id),
            ("Transaction Type", orig_type, new_type, orig_type != new_type),
            ("Quantity (Shares)", f"{orig_qty:,}", f"{new_qty:,}", orig_qty != new_qty),
            ("Price per Share", f"₹{orig_price:,.2f}", f"₹{new_price:,.2f}", orig_price != new_price),
            ("Total Trade Value", f"₹{orig_total:,.2f}", f"₹{new_total:,.2f}", abs(orig_total - new_total) > 0.001),
            ("Trade Date", orig_date, new_date, orig_date != new_date),
        ]

        self.table_compare.setRowCount(len(rows_data))

        for r_idx, (field_label, before_val, after_val, is_changed) in enumerate(rows_data):
            # 1. Field Name
            it_field = NumericTableWidgetItem(field_label)
            it_field.setFont(QFont("Segoe UI", 10, QFont.Bold if is_changed else QFont.Normal))
            it_field.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table_compare.setItem(r_idx, 0, it_field)

            # 2. Before
            it_before = NumericTableWidgetItem(before_val)
            it_before.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_before.setForeground(QColor("#64748B"))
            self.table_compare.setItem(r_idx, 1, it_before)

            # 3. After
            it_after = NumericTableWidgetItem(after_val)
            it_after.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if is_changed:
                it_after.setFont(QFont("Segoe UI", 10, QFont.Bold))
                it_after.setForeground(QColor("#0F172A"))
                it_after.setBackground(QColor("#FEF3C7"))  # Soft warm yellow highlight
            self.table_compare.setItem(r_idx, 2, it_after)

            # 4. Status / Change
            if is_changed:
                if field_label == "Quantity (Shares)":
                    diff = new_qty - orig_qty
                    status_text = f"+{diff:,} shares" if diff > 0 else f"{diff:,} shares"
                elif field_label == "Total Trade Value":
                    diff_val = new_total - orig_total
                    status_text = f"+₹{diff_val:,.2f}" if diff_val > 0 else f"-₹{abs(diff_val):,.2f}"
                else:
                    status_text = "Modified"
                it_status = NumericTableWidgetItem(status_text)
                it_status.setForeground(QColor("#D97706"))  # Amber
                it_status.setFont(QFont("Segoe UI", 10, QFont.Bold))
            else:
                it_status = NumericTableWidgetItem("Unchanged")
                it_status.setForeground(QColor("#94A3B8"))

            it_status.setTextAlignment(Qt.AlignCenter)
            self.table_compare.setItem(r_idx, 3, it_status)

        # Highlight Reason Note
        self.lbl_confirm_reason.setText(
            f"<b>Reason for Update:</b> <span style='color: #2563EB;'>{new_note}</span>"
        )

    def _save_changes(self):
        """Execute database update and emit notification."""
        err = self._validate_inputs()
        if err:
            QMessageBox.warning(self, "Invalid Input", err)
            self.tabs.setCurrentIndex(0)
            return

        acc_id = self.combo_account.currentData()
        sym = self.txt_symbol.text().strip().upper()
        tx_type = self.combo_type.currentData()
        qty = int(self.txt_qty.text().strip())
        price = float(self.txt_price.text().strip().replace("₹", "").replace(",", ""))
        date_str = f"{self.date_picker.date().toString('yyyy-MM-dd')} 00:00:00"
        note = self.combo_notes.currentText().strip()

        try:
            success = update_transaction(
                conn=self.db_conn,
                trade_id=self.trade_id,
                account_id=acc_id,
                symbol=sym,
                transaction_type=tx_type,
                quantity=qty,
                price=price,
                trade_date=date_str,
                notes=note,
            )
            if success:
                self.trade_updated.emit(self.trade_id)
                QMessageBox.information(
                    self,
                    "Transaction Updated",
                    f"Successfully updated trade {self.trade_id} ({sym}).\n"
                    f"Portfolio cost basis and holdings have been recalculated."
                )
                self.accept()
            else:
                QMessageBox.critical(self, "Update Failed", "Could not update the transaction in database.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save transaction changes:\n{e}")

