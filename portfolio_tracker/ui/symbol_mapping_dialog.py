"""Symbol Mapping Dialog: Map historical or renamed stock symbols to unified canonical tickers."""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import (
    add_symbol_mapping,
    delete_symbol_mapping,
    get_all_symbols,
    get_symbol_mappings,
)
from portfolio_tracker.ui.styles import NumericTableWidgetItem, set_style_class


class SymbolMappingDialog(QDialog):
    """Manage corporate action symbol changes (e.g., CADILAHC -> ZYDUSLIFE) to unify cost basis."""

    mapping_changed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.setWindowTitle("Symbol Name Changes & Corporate Actions Mapping")
        self.resize(860, 560)
        self.setModal(True)
        self._init_ui()
        self._refresh_autocomplete()
        self._load_mappings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header description
        lbl_title = QLabel("Stock Symbol Name Changes & Mergers")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        main_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "When a company renames its ticker symbol (e.g., CADILAHC → ZYDUSLIFE, MOTHERSUMI → MOTHERSON), "
            "historical buy trades under the old symbol and sell trades under the new symbol can cause "
            "false 'Sell > Buy' anomaly alerts. Map the old symbol to the new canonical symbol below to unify "
            "their transaction history and Adjusted Cost Basis (ACB)."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #475569; font-size: 12px; line-height: 1.4;")
        main_layout.addWidget(lbl_desc)

        # Input Card (Scoped CSS to prevent overriding child buttons)
        form_frame = QFrame()
        form_frame.setObjectName("symbol_form_frame")
        form_frame.setStyleSheet(
            "QFrame#symbol_form_frame { background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; }"
        )
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setSpacing(10)

        form_title = QLabel("Add New Symbol Mapping")
        form_title.setStyleSheet("font-weight: 600; color: #1E293B; font-size: 13px;")
        form_layout.addWidget(form_title)

        inputs_row = QHBoxLayout()
        inputs_row.setSpacing(10)

        # Source / Old Symbol
        col1 = QVBoxLayout()
        lbl_src = QLabel("Original / Old Symbol:")
        lbl_src.setStyleSheet("font-weight: 600; color: #475569; font-size: 11px;")
        self.combo_source = QComboBox()
        self.combo_source.setEditable(True)
        self.combo_source.setInsertPolicy(QComboBox.NoInsert)
        self.combo_source.setPlaceholderText("e.g. CADILAHC")
        col1.addWidget(lbl_src)
        col1.addWidget(self.combo_source)
        inputs_row.addLayout(col1, stretch=2)

        # Arrow indicator
        arrow_lbl = QLabel("➔")
        arrow_lbl.setStyleSheet("font-size: 18px; color: #64748B; font-weight: bold; margin-top: 14px;")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        inputs_row.addWidget(arrow_lbl)

        # Target / New Canonical Symbol
        col2 = QVBoxLayout()
        lbl_tgt = QLabel("Canonical / New Symbol:")
        lbl_tgt.setStyleSheet("font-weight: 600; color: #475569; font-size: 11px;")
        self.combo_target = QComboBox()
        self.combo_target.setEditable(True)
        self.combo_target.setInsertPolicy(QComboBox.NoInsert)
        self.combo_target.setPlaceholderText("e.g. ZYDUSLIFE")
        col2.addWidget(lbl_tgt)
        col2.addWidget(self.combo_target)
        inputs_row.addLayout(col2, stretch=2)

        # Notes
        col3 = QVBoxLayout()
        lbl_notes = QLabel("Reason / Notes (Optional):")
        lbl_notes.setStyleSheet("font-weight: 600; color: #475569; font-size: 11px;")
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. Renamed May 2022")
        col3.addWidget(lbl_notes)
        col3.addWidget(self.txt_notes)
        inputs_row.addLayout(col3, stretch=3)

        # Add Button
        col4 = QVBoxLayout()
        col4.addSpacing(16)
        self.btn_add = QPushButton("+ Add Mapping")
        set_style_class(self.btn_add, "primary-btn")
        self.btn_add.clicked.connect(self._add_mapping)
        col4.addWidget(self.btn_add)
        inputs_row.addLayout(col4, stretch=1)

        form_layout.addLayout(inputs_row)

        # Inline status message
        self.lbl_form_status = QLabel("")
        self.lbl_form_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #047857;")
        form_layout.addWidget(self.lbl_form_status)

        main_layout.addWidget(form_frame)

        # Existing Mappings Table
        lbl_table_hdr = QLabel("Configured Corporate Action Mappings")
        lbl_table_hdr.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 13px; margin-top: 6px;")
        main_layout.addWidget(lbl_table_hdr)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Original (Old) Symbol",
            "Canonical (New) Symbol",
            "Trades Affected",
            "Notes / Reason",
            "Action",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 230)
        self.table.setColumnWidth(4, 90)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setMinimumHeight(220)
        main_layout.addWidget(self.table)

        # Bottom Bar: Close button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        btn_close = QPushButton("Done")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)
        main_layout.addLayout(bottom_layout)

    def _refresh_autocomplete(self):
        """Populate comboboxes with all known stock symbols from database."""
        symbols = get_all_symbols(self.db_conn)
        self.combo_source.clear()
        self.combo_target.clear()
        for sym in symbols:
            self.combo_source.addItem(sym)
            self.combo_target.addItem(sym)
        self.combo_source.setCurrentIndex(-1)
        self.combo_target.setCurrentIndex(-1)

    def _load_mappings(self):
        """Fetch all symbol mappings and populate the table."""
        mappings = get_symbol_mappings(self.db_conn)
        self.table.setRowCount(len(mappings))

        for r_idx, m in enumerate(mappings):
            src_item = NumericTableWidgetItem(m["source_symbol"])
            src_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(r_idx, 0, src_item)

            tgt_item = NumericTableWidgetItem(m["target_symbol"])
            tgt_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(r_idx, 1, tgt_item)

            count_item = NumericTableWidgetItem(f"{m['trade_count']} trades")
            count_item.setData(Qt.UserRole, m["trade_count"])
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r_idx, 2, count_item)

            notes_item = NumericTableWidgetItem(m["notes"] or "-")
            notes_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(r_idx, 3, notes_item)

            # Action button: Delete mapping
            btn_del = QPushButton("Delete")
            set_style_class(btn_del, "danger-btn")
            btn_del.setStyleSheet(
                "QPushButton { background-color: #FEE2E2; color: #DC2626; border: 1px solid #FCA5A5; padding: 3px 8px; font-size: 11px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #DC2626; color: #FFFFFF; }"
            )
            src_sym = m["source_symbol"]
            btn_del.clicked.connect(lambda _, s=src_sym: self._delete_mapping(s))
            self.table.setCellWidget(r_idx, 4, btn_del)

    def _add_mapping(self):
        """Validate and add a new symbol mapping."""
        src = self.combo_source.currentText().strip().upper()
        tgt = self.combo_target.currentText().strip().upper()
        notes = self.txt_notes.text().strip()

        if not src or not tgt:
            self.lbl_form_status.setText("⚠️ Please provide both the original symbol and the new canonical symbol.")
            self.lbl_form_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #DC2626;")
            return

        if src == tgt:
            self.lbl_form_status.setText("⚠️ Original symbol and Canonical symbol cannot be identical.")
            self.lbl_form_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #DC2626;")
            return

        try:
            add_symbol_mapping(self.db_conn, src, tgt, notes)
            self._refresh_autocomplete()
            self._load_mappings()
            self.combo_source.setCurrentIndex(-1)
            self.combo_target.setCurrentIndex(-1)
            self.txt_notes.clear()
            self.lbl_form_status.setText(f"✓ Successfully mapped {src} ➔ {tgt}. All trades unified under {tgt}.")
            self.lbl_form_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #047857;")
            self.mapping_changed.emit()
        except Exception as e:
            self.lbl_form_status.setText(f"❌ Error: {str(e)}")
            self.lbl_form_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #DC2626;")

    def _delete_mapping(self, source_symbol: str):
        """Remove a mapping after confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete Mapping",
            f"Are you sure you want to remove the mapping for '{source_symbol}'?\n"
            f"Historical trades under '{source_symbol}' will no longer be mapped to its canonical symbol.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                delete_symbol_mapping(self.db_conn, source_symbol)
                self._load_mappings()
                self._refresh_autocomplete()
                self.mapping_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error Deleting Mapping", f"Failed to delete mapping:\n{str(e)}")
