"""Upload and ingestion view with responsive centered layout, drag-and-drop dropzone, and cross-platform styling."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from portfolio_tracker.parser import parse_tradebook
from portfolio_tracker.ui.account_manager_dialog import AccountManagerDialog
from portfolio_tracker.ui.manual_trade_dialog import ManualTradeDialog
from portfolio_tracker.ui.styles import configure_modern_calendar, set_style_class


class DropZoneWidget(QFrame):
    """Modern drag-and-drop file upload target widget."""

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

        self.lbl_icon = QLabel("↑")
        self.lbl_icon.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #2563EB; "
            "background-color: #DBEAFE; border-radius: 24px; "
            "min-width: 48px; max-width: 48px; min-height: 48px; max-height: 48px;"
        )
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignCenter)

        self.lbl_main = QLabel("Drag & drop your Zerodha Tradebook file here")
        self.lbl_main.setStyleSheet("font-size: 15px; font-weight: 600; color: #1E293B; background: transparent;")
        self.lbl_main.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_main)

        self.lbl_sub = QLabel("Supports Excel (.xlsx, .xls) and CSV (.csv) exports")
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
            if urls:
                fpath = urls[0].toLocalFile()
                ext = Path(fpath).suffix.lower()
                if ext in (".xlsx", ".xls", ".csv"):
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
        if urls:
            fpath = urls[0].toLocalFile()
            ext = Path(fpath).suffix.lower()
            if ext in (".xlsx", ".xls", ".csv"):
                event.acceptProposedAction()
                self.file_dropped.emit(fpath)
                return
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._browse_file()

    def _browse_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Zerodha Tradebook File",
            str(Path.home()),
            "Excel & CSV Tradebooks (*.xlsx *.xls *.csv);;All Files (*.*)",
        )
        if fpath:
            self.file_dropped.emit(fpath)


class UploadView(QWidget):
    """Responsive, senior-friendly tradebook ingestion view that scales perfectly across all screen resolutions."""

    import_completed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.selected_file_path: str = ""
        self._init_ui()
        self.refresh_accounts()

    def _init_ui(self):
        # Root layout with QScrollArea for absolute responsiveness on all screen sizes
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

        # Centered container with max-width for web-dashboard aesthetic
        container = QWidget()
        container.setMaximumWidth(860)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(16)

        # ------------------------------------------------------------------
        # Header Banner
        # ------------------------------------------------------------------
        header_card = QFrame()
        header_card.setProperty("class", "step-card")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(20, 18, 20, 18)
        h_layout.setSpacing(6)

        title = QLabel("Import Zerodha Tradebook")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        h_layout.addWidget(title)

        subtitle = QLabel(
            "Upload your historical Tradebook files (.xlsx, .xls, .csv) exported from Zerodha Console. "
            "Our engine automatically detects table headers, eliminates duplicate records, and computes your house-money basis."
        )
        subtitle.setStyleSheet("color: #475569; font-size: 13px; line-height: 1.4;")
        subtitle.setWordWrap(True)
        h_layout.addWidget(subtitle)
        container_layout.addWidget(header_card)

        # ------------------------------------------------------------------
        # Step 1: Destination Account
        # ------------------------------------------------------------------
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

        s1_desc = QLabel("Trades imported from this file will be credited to this individual family member account.")
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

        self.btn_manual_trade = QPushButton("+ Add Manual Trade")
        set_style_class(self.btn_manual_trade, "primary-btn")
        self.btn_manual_trade.setMinimumHeight(38)
        self.btn_manual_trade.setToolTip("Record off-market, IPO, corporate action, or manual trade")
        self.btn_manual_trade.clicked.connect(self._open_manual_trade)
        acc_controls.addWidget(self.btn_manual_trade)
        s1_layout.addLayout(acc_controls)

        # Cutoff Date / Calendar control on Import tab
        date_controls = QHBoxLayout()
        date_controls.setSpacing(10)

        lbl_date = QLabel("Cutoff Date:")
        lbl_date.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155;")
        date_controls.addWidget(lbl_date)

        self.date_filter = QDateEdit()
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.setCalendarPopup(True)
        configure_modern_calendar(self.date_filter.calendarWidget())
        self.date_filter.setDisplayFormat("yyyy-MM-dd")
        self.date_filter.setMinimumWidth(130)
        self.date_filter.setMinimumHeight(36)
        self.date_filter.setToolTip("Target cutoff date for portfolio ledger sync")
        date_controls.addWidget(self.date_filter)

        lbl_date_hint = QLabel("• All trades up to this cutoff date are computed into effective cost basis")
        lbl_date_hint.setStyleSheet("font-size: 12px; color: #64748B;")
        date_controls.addWidget(lbl_date_hint)
        date_controls.addStretch()
        s1_layout.addLayout(date_controls)

        container_layout.addWidget(step1_card)

        # ------------------------------------------------------------------
        # Step 2: Choose File & Dropzone
        # ------------------------------------------------------------------
        step2_card = QFrame()
        step2_card.setProperty("class", "step-card")
        s2_layout = QVBoxLayout(step2_card)
        s2_layout.setContentsMargins(20, 18, 20, 18)
        s2_layout.setSpacing(12)

        s2_header = QHBoxLayout()
        num2 = QLabel("2")
        num2.setProperty("class", "step-number")
        s2_header.addWidget(num2)

        lbl_s2 = QLabel("Select or Drag & Drop File")
        lbl_s2.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        s2_header.addWidget(lbl_s2)
        s2_header.addStretch()
        s2_layout.addLayout(s2_header)

        # Drag and Drop Target
        self.drop_zone = DropZoneWidget()
        self.drop_zone.file_dropped.connect(self._set_selected_file)
        s2_layout.addWidget(self.drop_zone)

        # Selected File Preview Card
        self.file_card = QFrame()
        self.file_card.setProperty("class", "file-info-card")
        self.file_card.setVisible(False)
        fc_layout = QHBoxLayout(self.file_card)
        fc_layout.setContentsMargins(14, 12, 14, 12)

        file_text_box = QVBoxLayout()
        file_text_box.setSpacing(3)
        self.lbl_file_name = QLabel("")
        self.lbl_file_name.setStyleSheet("font-weight: 700; color: #0F172A; font-size: 14px;")
        file_text_box.addWidget(self.lbl_file_name)

        self.lbl_file_meta = QLabel("")
        self.lbl_file_meta.setStyleSheet("color: #059669; font-size: 12px; font-weight: 500;")
        file_text_box.addWidget(self.lbl_file_meta)
        fc_layout.addLayout(file_text_box, 1)

        self.btn_change_file = QPushButton("Change File")
        self.btn_change_file.clicked.connect(self.drop_zone._browse_file)
        fc_layout.addWidget(self.btn_change_file)

        s2_layout.addWidget(self.file_card)
        container_layout.addWidget(step2_card)

        # ------------------------------------------------------------------
        # Step 3: Process & Import Action Button
        # ------------------------------------------------------------------
        step3_card = QFrame()
        step3_card.setProperty("class", "step-card")
        s3_layout = QVBoxLayout(step3_card)
        s3_layout.setContentsMargins(20, 18, 20, 18)
        s3_layout.setSpacing(14)

        s3_header = QHBoxLayout()
        num3 = QLabel("3")
        num3.setProperty("class", "step-number")
        s3_header.addWidget(num3)

        lbl_s3 = QLabel("Start Ingestion & Deduplication")
        lbl_s3.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        s3_header.addWidget(lbl_s3)
        s3_header.addStretch()
        s3_layout.addLayout(s3_header)

        self.btn_import = QPushButton("Import & Process Trades")
        set_style_class(self.btn_import, "success-btn")
        self.btn_import.setMinimumHeight(44)
        self.btn_import.setStyleSheet(
            "font-size: 15px; font-weight: 700; border-radius: 8px; background-color: #059669; color: #FFFFFF;"
        )
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._start_import)
        s3_layout.addWidget(self.btn_import)

        container_layout.addWidget(step3_card)

        # ------------------------------------------------------------------
        # Ingestion Feedback Banner Card
        # ------------------------------------------------------------------
        self.status_card = QFrame()
        self.status_card.setStyleSheet(
            "background-color: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 10px; padding: 18px;"
        )
        self.status_card.setVisible(False)
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setSpacing(6)

        self.lbl_status_title = QLabel("Ingestion Completed Successfully")
        self.lbl_status_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #15803D;")
        status_layout.addWidget(self.lbl_status_title)

        self.lbl_status_detail = QLabel("")
        self.lbl_status_detail.setStyleSheet("font-size: 13px; color: #166534; line-height: 1.5;")
        self.lbl_status_detail.setWordWrap(True)
        status_layout.addWidget(self.lbl_status_detail)

        container_layout.addWidget(self.status_card)

        # ------------------------------------------------------------------
        # Zerodha Guide & Manual Entry Card
        # ------------------------------------------------------------------
        guide_card = QFrame()
        guide_card.setProperty("class", "step-card")
        guide_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 18px;")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setSpacing(10)

        guide_title = QLabel("How to Download your Tradebook from Zerodha")
        guide_title.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 14px;")
        guide_layout.addWidget(guide_title)

        steps_text = (
            "1. Log into your Zerodha account at <b>console.zerodha.com</b>.<br>"
            "2. Navigate to <b>Reports</b> in the top navigation bar and select <b>Tradebook</b>.<br>"
            "3. Select Segment: <b>EQ (Equity)</b>, choose your desired date range, and click <b>Download XLSX / CSV</b>.<br>"
            "4. Upload the downloaded file directly here."
        )
        lbl_guide_steps = QLabel(steps_text)
        lbl_guide_steps.setStyleSheet("color: #475569; font-size: 13px; line-height: 1.5;")
        lbl_guide_steps.setWordWrap(True)
        guide_layout.addWidget(lbl_guide_steps)

        guide_layout.addSpacing(6)

        manual_row = QHBoxLayout()
        lbl_manual_hint = QLabel("Need to record an off-market transfer, corporate action, or missing trade?")
        lbl_manual_hint.setStyleSheet("color: #64748B; font-size: 13px;")
        manual_row.addWidget(lbl_manual_hint)
        manual_row.addStretch()

        self.btn_manual_trade_guide = QPushButton("+ Add Manual Trade")
        set_style_class(self.btn_manual_trade_guide, "primary-btn")
        self.btn_manual_trade_guide.clicked.connect(self._open_manual_trade)
        manual_row.addWidget(self.btn_manual_trade_guide)
        guide_layout.addLayout(manual_row)

        container_layout.addWidget(guide_card)

        scroll_layout.addWidget(container)
        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area)

    def refresh_accounts(self):
        """Populate destination accounts combobox."""
        current = self.combo_account.currentData()
        self.combo_account.clear()
        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            self.combo_account.addItem(f"{acc['user_name']} ({acc['account_id']})", acc["account_id"])

        idx = self.combo_account.findData(current)
        if idx >= 0:
            self.combo_account.setCurrentIndex(idx)

    def _set_selected_file(self, fpath: str):
        """Update UI with selected file details."""
        if not fpath or not Path(fpath).is_file():
            return

        self.selected_file_path = fpath
        p = Path(fpath)
        try:
            size_kb = os.path.getsize(p) / 1024.0
            size_str = f"{size_kb:,.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):,.2f} MB"
        except Exception:
            size_str = ""

        self.lbl_file_name.setText(f"File: {p.name}")
        self.lbl_file_meta.setText(f"Ready for ingestion • {size_str} • {p.suffix.upper()[1:]} File")
        self.file_card.setVisible(True)
        self.drop_zone.setVisible(False)
        self.btn_import.setEnabled(True)

    def _start_import(self):
        if not self.selected_file_path or not Path(self.selected_file_path).is_file():
            QMessageBox.warning(self, "No File", "Please select a valid tradebook file first.")
            return

        target_acc_id = self.combo_account.currentData()
        target_name = self.combo_account.currentText()

        try:
            inserted, dupes, total = parse_tradebook(
                file_path=self.selected_file_path,
                account_id=target_acc_id,
                db_conn=self.db_conn,
            )

            # Display Status Banner
            self.status_card.setVisible(True)
            self.status_card.setStyleSheet(
                "background-color: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 10px; padding: 18px;"
            )
            self.lbl_status_title.setText(f"Ingestion Completed for {target_name}")
            self.lbl_status_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #15803D;")
            self.lbl_status_detail.setText(
                f"• Processed: {total} total trade executions.\n"
                f"• Added: {inserted} new transactions inserted.\n"
                f"• Deduplicated: {dupes} duplicate entries automatically skipped."
            )
            self.lbl_status_detail.setStyleSheet("font-size: 13px; color: #166534; line-height: 1.5;")

            # Reset file card and dropzone
            self.file_card.setVisible(False)
            self.drop_zone.setVisible(True)
            self.selected_file_path = ""
            self.btn_import.setEnabled(False)

            # Signal dashboard to reload
            self.import_completed.emit()

            QMessageBox.information(
                self,
                "Import Successful",
                f"Successfully processed {target_name}:\n\n"
                f"• Added: {inserted} new trades\n"
                f"• Duplicates skipped: {dupes}\n"
                f"• Total processed: {total}",
            )

        except Exception as e:
            self.status_card.setVisible(True)
            self.status_card.setStyleSheet(
                "background-color: #FEF2F2; border: 1.5px solid #FCA5A5; border-radius: 10px; padding: 18px;"
            )
            self.lbl_status_title.setText("Ingestion Failed")
            self.lbl_status_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #B91C1C;")
            self.lbl_status_detail.setText(str(e))
            self.lbl_status_detail.setStyleSheet("font-size: 13px; color: #991B1B;")

            QMessageBox.critical(self, "Import Error", f"Failed to ingest tradebook file:\n{e}")

    def _open_account_manager(self):
        dlg = AccountManagerDialog(self.db_conn, self)
        dlg.accounts_changed.connect(self.refresh_accounts)
        dlg.exec()

    def _open_manual_trade(self):
        acc_id = self.combo_account.currentData()
        dlg = ManualTradeDialog(self.db_conn, default_account_id=acc_id, parent=self)
        dlg.trade_added.connect(self.import_completed.emit)
        dlg.exec()
