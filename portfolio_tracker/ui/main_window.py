"""Main application window shell with header bar, tab navigation, and clean termination lifecycle."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.config import get_active_db_path
from portfolio_tracker.ui.holdings_view import HoldingsView
from portfolio_tracker.ui.styles import set_style_class
from portfolio_tracker.ui.upload_view import UploadView


class MainWindow(QMainWindow):
    """Main window shell for Portfolio Tracker."""

    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__()
        self.db_conn = db_conn
        self.setWindowTitle("Stock ACB Portfolio Tracker")
        self.setMinimumSize(1100, 750)
        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setObjectName("app_header")
        header.setStyleSheet("QFrame#app_header { background-color: #0F172A; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 14, 24, 14)

        # App Brand & Title
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_app_name = QLabel("Stock ACB Portfolio Tracker")
        lbl_app_name.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF; background: transparent;")
        title_box.addWidget(lbl_app_name)

        lbl_app_sub = QLabel("Adjusted Cost Basis (ACB) & Multi-Account Family Ledger")
        lbl_app_sub.setStyleSheet("font-size: 12px; color: #94A3B8; background: transparent;")
        title_box.addWidget(lbl_app_sub)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Header Right Actions: Merged DB Settings Button & Top Close Button
        header_actions = QHBoxLayout()
        header_actions.setSpacing(10)

        active_db = get_active_db_path()
        self.btn_db_settings = QPushButton(f"● Database: {active_db.name} ⚙")
        self.btn_db_settings.setObjectName("btn_top_db")
        self.btn_db_settings.setToolTip(
            f"Active SQLite File:\n{active_db}\n\nClick to manage database location, backup, or restore."
        )
        self.btn_db_settings.setStyleSheet(
            """
            QPushButton#btn_top_db {
                background-color: #1E293B;
                color: #38BDF8;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 14px;
                border: 1px solid #334155;
                min-height: 20px;
            }
            QPushButton#btn_top_db:hover {
                background-color: #334155;
                color: #7DD3FC;
                border-color: #38BDF8;
            }
            """
        )
        self.btn_db_settings.clicked.connect(self._open_storage_settings)
        header_actions.addWidget(self.btn_db_settings)

        self.btn_close = QPushButton("✕ Close")
        self.btn_close.setObjectName("btn_top_close")
        set_style_class(self.btn_close, "danger-btn")
        self.btn_close.setToolTip("Safely close the application")
        self.btn_close.setStyleSheet(
            """
            QPushButton#btn_top_close {
                background-color: #DC2626;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 14px;
                border: 1px solid #DC2626;
                min-height: 20px;
            }
            QPushButton#btn_top_close:hover {
                background-color: #B91C1C;
                border-color: #B91C1C;
            }
            """
        )
        self.btn_close.clicked.connect(self.close)
        header_actions.addWidget(self.btn_close)

        header_layout.addLayout(header_actions)

        main_layout.addWidget(header)

        # Central Tabs
        self.tabs = QTabWidget()
        self.tabs.setContentsMargins(16, 12, 16, 16)

        # Tab 1: Holdings Dashboard
        self.holdings_view = HoldingsView(self.db_conn, self)
        self.tabs.addTab(self.holdings_view, "Holdings Dashboard")

        # Tab 2: Upload Tradebook
        self.upload_view = UploadView(self.db_conn, self)
        self.tabs.addTab(self.upload_view, "Import Tradebook")

        main_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central_widget)

        # Cross-View Signals Wiring
        self.upload_view.import_completed.connect(self._on_import_done)
        self.holdings_view.data_changed.connect(self.upload_view.refresh_accounts)
        self.upload_view.date_filter.dateChanged.connect(self.holdings_view.date_cutoff.setDate)
        self.holdings_view.date_cutoff.dateChanged.connect(self.upload_view.date_filter.setDate)

    def _open_storage_settings(self):
        """Open storage settings dialog and refresh database indicator in header bar."""
        from portfolio_tracker.ui.storage_settings_dialog import StorageSettingsDialog
        dlg = StorageSettingsDialog(self)
        dlg.exec()
        active_db = get_active_db_path()
        self.btn_db_settings.setText(f"● Database: {active_db.name} ⚙")
        self.btn_db_settings.setToolTip(
            f"Active SQLite File:\n{active_db}\n\nClick to manage database location, backup, or restore."
        )

    def _on_import_done(self):
        """When an import completes on the Upload tab, refresh the dashboard and switch to it."""
        self.holdings_view.refresh_data()
        self.tabs.setCurrentIndex(0)

    def closeEvent(self, event):
        """Clean shutdown handler ensuring zero orphan background processes or locks."""
        try:
            self.db_conn.close()
        except Exception:
            pass
        event.accept()

