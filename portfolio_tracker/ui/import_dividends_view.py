"""Import and ingestion view for Zerodha dividend statements with drag-and-drop dropzone."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import get_accounts
from portfolio_tracker.dividend_parser import (
    extract_client_id_from_metadata,
    parse_dividend_file,
)
from portfolio_tracker.ui.account_manager_dialog import AccountManagerDialog
from portfolio_tracker.ui.manual_dividend_dialog import ManualDividendDialog
from portfolio_tracker.ui.styles import set_style_class


class DividendDropZoneWidget(QFrame):
    """Drag-and-drop file upload target widget for dividend spreadsheets."""

    files_dropped = Signal(list)
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setProperty("class", "drop-zone")
        self.setCursor(Qt.PointingHandCursor)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self.lbl_icon = QLabel("💰")
        self.lbl_icon.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #059669; "
            "background-color: #D1FAE5; border-radius: 24px; "
            "min-width: 48px; max-width: 48px; min-height: 48px; max-height: 48px;"
        )
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignCenter)

        self.lbl_main = QLabel("Drag & drop your Zerodha Dividend Statement file(s) here")
        self.lbl_main.setStyleSheet("font-size: 15px; font-weight: 600; color: #1E293B; background: transparent;")
        self.lbl_main.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_main)

        self.lbl_sub = QLabel("Supports Excel (.xlsx, .xls) and CSV (.csv) exports • Select single or multiple FY files")
        self.lbl_sub.setStyleSheet("font-size: 13px; color: #64748B; background: transparent;")
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_sub)

        layout.addSpacing(6)

        self.btn_browse = QPushButton("Browse Files")
        set_style_class(self.btn_browse, "primary-btn")
        self.btn_browse.setFixedWidth(140)
        self.btn_browse.clicked.connect(self._browse_file)
        layout.addWidget(self.btn_browse, alignment=Qt.AlignCenter)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid = [
                u.toLocalFile()
                for u in urls
                if Path(u.toLocalFile()).suffix.lower() in (".xlsx", ".xls", ".csv")
            ]
            if valid:
                event.acceptProposedAction()
                self.setProperty("class", "drop-zone-active")
                self.style().unpolish(self)
                self.style().polish(self)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("class", "drop-zone")
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self.setProperty("class", "drop-zone")
        self.style().unpolish(self)
        self.style().polish(self)

        urls = event.mimeData().urls()
        valid = [
            u.toLocalFile()
            for u in urls
            if Path(u.toLocalFile()).suffix.lower() in (".xlsx", ".xls", ".csv")
        ]
        if valid:
            event.acceptProposedAction()
            self.files_dropped.emit(valid)
            self.file_dropped.emit(valid[0])
            return
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._browse_file()

    def _browse_file(self):
        fpaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Zerodha Dividend File(s)",
            str(Path.home()),
            "Dividend Files (*.csv *.xlsx *.xls);;All Files (*.*)",
        )
        if fpaths:
            self.files_dropped.emit(fpaths)
            self.file_dropped.emit(fpaths[0])


class ImportDividendsView(QWidget):
    """Responsive view for uploading and batch-ingesting Zerodha dividend files."""

    import_completed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.selected_file_paths: List[str] = []
        self._init_ui()
        self.refresh_accounts()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(24, 24, 24, 32)
        scroll_layout.setSpacing(18)
        scroll_layout.setAlignment(Qt.AlignHCenter)

        container = QWidget()
        container.setMaximumWidth(860)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(16)

        # ----------------------------------------------------
        # Header Banner
        # ----------------------------------------------------
        header_card = QFrame()
        header_card.setProperty("class", "step-card")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(20, 18, 20, 18)
        h_layout.setSpacing(6)

        title = QLabel("Import Zerodha Dividend Statements")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        h_layout.addWidget(title)

        subtitle = QLabel(
            "Upload your historical Dividend statements (.csv, .xlsx) exported from Zerodha Console. "
            "Dividends are sandboxed on the dedicated Dividends Dashboard and will not alter your holding calculations."
        )
        subtitle.setStyleSheet("color: #475569; font-size: 13px; line-height: 1.4;")
        subtitle.setWordWrap(True)
        h_layout.addWidget(subtitle)
        container_layout.addWidget(header_card)

        # ----------------------------------------------------
        # Step 1: Target Family Account
        # ----------------------------------------------------
        step1_card = QFrame()
        step1_card.setProperty("class", "step-card")
        s1_layout = QVBoxLayout(step1_card)
        s1_layout.setContentsMargins(20, 18, 20, 18)
        s1_layout.setSpacing(12)

        s1_header = QHBoxLayout()
        num1 = QLabel("1")
        num1.setProperty("class", "step-number")
        s1_header.addWidget(num1)

        lbl_s1 = QLabel("Select Target Family Member Account")
        lbl_s1.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        s1_header.addWidget(lbl_s1)
        s1_header.addStretch()
        s1_layout.addLayout(s1_header)

        s1_desc = QLabel("Dividends imported from this file will be credited to this individual family member account.")
        s1_desc.setStyleSheet("color: #64748B; font-size: 13px;")
        s1_layout.addWidget(s1_desc)

        acc_controls = QHBoxLayout()
        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        self.combo_account.setMinimumWidth(280)
        self.combo_account.setMinimumHeight(38)
        acc_controls.addWidget(self.combo_account, 1)

        self.btn_manage_acc = QPushButton("Manage Accounts")
        self.btn_manage_acc.setMinimumHeight(38)
        self.btn_manage_acc.clicked.connect(self._open_account_manager)
        acc_controls.addWidget(self.btn_manage_acc)

        self.btn_manual_div = QPushButton("+ Add Manual Dividend")
        set_style_class(self.btn_manual_div, "primary-btn")
        self.btn_manual_div.setMinimumHeight(38)
        self.btn_manual_div.setToolTip("Record an off-market dividend or manual credit")
        self.btn_manual_div.clicked.connect(self._open_manual_dividend)
        acc_controls.addWidget(self.btn_manual_div)
        s1_layout.addLayout(acc_controls)

        container_layout.addWidget(step1_card)

        # ----------------------------------------------------
        # Step 2: Upload Files Dropzone
        # ----------------------------------------------------
        step2_card = QFrame()
        step2_card.setProperty("class", "step-card")
        s2_layout = QVBoxLayout(step2_card)
        s2_layout.setContentsMargins(20, 18, 20, 18)
        s2_layout.setSpacing(12)

        s2_header = QHBoxLayout()
        num2 = QLabel("2")
        num2.setProperty("class", "step-number")
        s2_header.addWidget(num2)

        lbl_s2 = QLabel("Upload Dividend Statement(s)")
        lbl_s2.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        s2_header.addWidget(lbl_s2)
        s2_header.addStretch()
        s2_layout.addLayout(s2_header)

        self.drop_zone = DividendDropZoneWidget()
        self.drop_zone.files_dropped.connect(self._on_files_selected)
        s2_layout.addWidget(self.drop_zone)

        # Selected files indicator
        self.files_box = QFrame()
        self.files_box.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;"
        )
        self.files_box.hide()
        fb_layout = QVBoxLayout(self.files_box)
        fb_layout.setContentsMargins(8, 8, 8, 8)
        fb_layout.setSpacing(6)

        self.lbl_selected_files = QLabel()
        self.lbl_selected_files.setStyleSheet("font-size: 13px; font-weight: 600; color: #0F172A;")
        fb_layout.addWidget(self.lbl_selected_files)

        self.btn_clear_files = QPushButton("Clear Selection")
        self.btn_clear_files.setFixedWidth(120)
        self.btn_clear_files.clicked.connect(self._clear_files)
        fb_layout.addWidget(self.btn_clear_files)
        s2_layout.addWidget(self.files_box)

        # Import action button
        self.btn_process = QPushButton("🚀 Process & Ingest Dividends")
        set_style_class(self.btn_process, "primary-btn")
        self.btn_process.setMinimumHeight(44)
        self.btn_process.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self._process_import)
        s2_layout.addWidget(self.btn_process)

        container_layout.addWidget(step2_card)

        # ----------------------------------------------------
        # Result Feedback Card
        # ----------------------------------------------------
        self.result_card = QFrame()
        self.result_card.setStyleSheet(
            "background-color: #F0FDF4; border: 1.5px solid #16A34A; border-radius: 8px; padding: 14px 18px;"
        )
        self.result_card.hide()
        rc_layout = QVBoxLayout(self.result_card)
        rc_layout.setContentsMargins(0, 0, 0, 0)
        rc_layout.setSpacing(6)

        self.lbl_result_title = QLabel("Import Successful!")
        self.lbl_result_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #166534;")
        rc_layout.addWidget(self.lbl_result_title)

        self.lbl_result_body = QLabel()
        self.lbl_result_body.setStyleSheet("font-size: 13px; color: #15803D;")
        self.lbl_result_body.setWordWrap(True)
        rc_layout.addWidget(self.lbl_result_body)

        container_layout.addWidget(self.result_card)

        scroll_layout.addWidget(container)
        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area)

    def refresh_accounts(self):
        """Populate the account combo box with latest active accounts from SQLite."""
        current_data = self.combo_account.currentData()
        self.combo_account.clear()
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            label = f"{acc['user_name']} ({acc['account_id']})"
            self.combo_account.addItem(label, acc["account_id"])

        if current_data:
            idx = self.combo_account.findData(current_data)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)

    def _open_account_manager(self):
        dlg = AccountManagerDialog(self.db_conn, self)
        dlg.exec()
        self.refresh_accounts()

    def _open_manual_dividend(self):
        acc_id = self.combo_account.currentData()
        dlg = ManualDividendDialog(self.db_conn, default_account_id=acc_id, parent=self)
        dlg.dividend_saved.connect(self.import_completed.emit)
        dlg.exec()

    def _on_files_selected(self, file_paths: List[str]):
        valid_paths = [p for p in file_paths if Path(p).is_file()]
        if not valid_paths:
            return

        self.selected_file_paths = valid_paths
        names = [Path(p).name for p in valid_paths]
        self.lbl_selected_files.setText(f"📁 Selected ({len(names)} file{'s' if len(names) > 1 else ''}): " + ", ".join(names))
        self.files_box.show()
        self.btn_process.setEnabled(True)
        self.result_card.hide()

        # Auto-detect Client ID from the first file's metadata
        detected_id = extract_client_id_from_metadata(valid_paths[0])
        if detected_id:
            idx = self.combo_account.findData(detected_id)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)

    def _clear_files(self):
        self.selected_file_paths = []
        self.files_box.hide()
        self.btn_process.setEnabled(False)
        self.result_card.hide()

    def _process_import(self):
        if not self.selected_file_paths:
            return

        acc_id = self.combo_account.currentData()
        if not acc_id:
            QMessageBox.warning(self, "No Account Selected", "Please select a target family account.")
            return

        total_inserted = 0
        total_dups = 0
        total_rows = 0
        errors: List[str] = []

        for fpath in self.selected_file_paths:
            try:
                ins, dups, tot = parse_dividend_file(
                    file_path=fpath,
                    account_id=acc_id,
                    db_conn=self.db_conn,
                )
                total_inserted += ins
                total_dups += dups
                total_rows += tot
            except Exception as e:
                errors.append(f"{Path(fpath).name}: {str(e)}")

        if errors:
            err_msg = "\n".join(errors)
            QMessageBox.critical(self, "Parsing Errors Occurred", f"Some files could not be imported:\n\n{err_msg}")

        # Feedback
        self.lbl_result_title.setText("🎉 Import Completed Successfully!")
        self.lbl_result_body.setText(
            f"Processed {len(self.selected_file_paths)} file(s) for account '{acc_id}':\n"
            f"• {total_inserted} new dividend records credited\n"
            f"• {total_dups} duplicate records skipped safely\n"
            f"• {total_rows} total rows scanned"
        )
        self.result_card.show()
        self._clear_files()
        self.import_completed.emit()

