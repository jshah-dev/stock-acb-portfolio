"""Dialog for managing family accounts (add & remove accounts with safety confirmations)."""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
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

from portfolio_tracker.db import (
    add_account,
    delete_account,
    get_account_transaction_count,
    get_accounts,
)
from portfolio_tracker.ui.styles import NumericTableWidgetItem, set_style_class


class AccountManagerDialog(QDialog):
    """Senior-friendly modal dialog to add and safely delete family accounts."""

    accounts_changed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.setWindowTitle("Manage Family Accounts")
        self.setMinimumSize(580, 440)
        self._init_ui()
        self._load_accounts()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header info
        title_label = QLabel("Family Portfolios & Accounts")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Add family member accounts to track combined house-money averages. "
            "Deleting an account will safely delete all its associated transactions."
        )
        desc_label.setStyleSheet("color: #64748B; font-size: 13px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Accounts Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Account ID", "Display Name", "Broker", "Trades Count"])
        header = self.table.horizontalHeader()
        header.setToolTip("Click any column header to sort. Drag column dividers to resize.")
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Action Buttons row
        btn_layout = QHBoxLayout()
        self.btn_autofit = QPushButton("↔ Auto-Fit Columns")
        self.btn_autofit.setToolTip("Auto-fit columns while keeping user drag resizing")
        self.btn_autofit.clicked.connect(self._auto_fit_columns)
        btn_layout.addWidget(self.btn_autofit)

        btn_layout.addStretch()

        self.btn_delete = QPushButton("Remove Selected Account")
        set_style_class(self.btn_delete, "danger-btn")
        self.btn_delete.clicked.connect(self._on_delete_account)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        # Add Account Section
        add_title = QLabel("Add New Family Account")
        add_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #1E293B; margin-top: 8px;")
        layout.addWidget(add_title)

        form_layout = QFormLayout()
        self.txt_acc_id = QLineEdit()
        self.txt_acc_id.setPlaceholderText("e.g. ZERODHA_MOM")
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Mother's Zerodha")
        self.txt_broker = QLineEdit("Zerodha")

        form_layout.addRow("Account ID:", self.txt_acc_id)
        form_layout.addRow("Display Name:", self.txt_name)
        form_layout.addRow("Broker:", self.txt_broker)
        layout.addLayout(form_layout)

        add_btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Account")
        set_style_class(self.btn_add, "primary-btn")
        self.btn_add.clicked.connect(self._on_add_account)
        add_btn_layout.addStretch()
        add_btn_layout.addWidget(self.btn_add)
        layout.addLayout(add_btn_layout)

    def _auto_fit_columns(self):
        """Auto-fit column widths while preserving interactive resizing."""
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _load_accounts(self):
        """Populate table with current accounts from database with numeric sorting."""
        self.table.setSortingEnabled(False)
        accounts = get_accounts(self.db_conn)
        self.table.setRowCount(len(accounts))

        for r_idx, acc in enumerate(accounts):
            it_id = NumericTableWidgetItem(acc["account_id"])
            it_id.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)

            it_name = NumericTableWidgetItem(acc["user_name"])
            it_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)

            it_broker = NumericTableWidgetItem(acc["broker"])
            it_broker.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_broker.setFlags(it_broker.flags() & ~Qt.ItemIsEditable)

            tx_count = int(acc["transaction_count"])
            it_count = NumericTableWidgetItem(str(tx_count))
            it_count.setData(Qt.UserRole, tx_count)
            it_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_count.setFlags(it_count.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(r_idx, 0, it_id)
            self.table.setItem(r_idx, 1, it_name)
            self.table.setItem(r_idx, 2, it_broker)
            self.table.setItem(r_idx, 3, it_count)

        self.table.setSortingEnabled(True)

    def _on_add_account(self):
        acc_id = self.txt_acc_id.text().strip().upper()
        name = self.txt_name.text().strip()
        broker = self.txt_broker.text().strip() or "Zerodha"

        if not acc_id or not name:
            QMessageBox.warning(self, "Missing Fields", "Please enter both an Account ID and a Display Name.")
            return

        try:
            add_account(self.db_conn, acc_id, name, broker)
            self.txt_acc_id.clear()
            self.txt_name.clear()
            self._load_accounts()
            self.accounts_changed.emit()
            QMessageBox.information(self, "Success", f"Account '{name}' added successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not add account:\n{e}")

    def _on_delete_account(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Account", "Please select an account row to delete.")
            return

        row_idx = selected_rows[0].row()
        acc_id = self.table.item(row_idx, 0).text()
        user_name = self.table.item(row_idx, 1).text()
        tx_count = get_account_transaction_count(self.db_conn, acc_id)

        # Check total accounts count
        accounts = get_accounts(self.db_conn)
        if len(accounts) <= 1:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "You cannot delete the only remaining account in your portfolio."
            )
            return

        confirm_msg = (
            f"Are you sure you want to permanently remove account '{user_name}'?\n\n"
            f"⚠️ Warning: This will delete {tx_count} associated trade transaction(s).\n"
            "This action cannot be undone."
        )

        reply = QMessageBox.question(
            self,
            "Confirm Account Deletion",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                delete_account(self.db_conn, acc_id)
                self._load_accounts()
                self.accounts_changed.emit()
                QMessageBox.information(
                    self,
                    "Account Deleted",
                    f"Account '{user_name}' and its {tx_count} trade(s) were removed."
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete account:\n{e}")

