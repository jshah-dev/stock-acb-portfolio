"""Storage settings dialog for custom database locations (Google Drive / OneDrive) and backup/restore."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from portfolio_tracker.config import get_active_db_path, set_custom_db_path
from portfolio_tracker.db import backup_database, restore_database


class StorageSettingsDialog(QDialog):
    """Dialog allowing users to store portfolio.db in Google Drive/OneDrive and trigger live backups."""

    db_reloaded = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self.setWindowTitle("Database Location & Backups")
        self.setMinimumSize(560, 420)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(24, 24, 24, 24)

        # 1. Custom Location Section
        group_loc = QGroupBox("Database Storage Location (Cloud Backup)")
        group_loc.setStyleSheet("font-weight: 600; font-size: 13px;")
        loc_layout = QVBoxLayout(group_loc)
        loc_layout.setSpacing(10)

        loc_desc = QLabel(
            "You can store your portfolio database inside your Google Drive, OneDrive, or Dropbox folder "
            "so your data is automatically synced and backed up to the cloud."
        )
        loc_desc.setStyleSheet("color: #64748B; font-weight: normal; font-size: 12px;")
        loc_desc.setWordWrap(True)
        loc_layout.addWidget(loc_desc)

        path_layout = QHBoxLayout()
        self.txt_db_path = QLineEdit(str(get_active_db_path()))
        self.txt_db_path.setReadOnly(True)
        path_layout.addWidget(self.txt_db_path)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._on_browse_location)
        path_layout.addWidget(self.btn_browse)
        loc_layout.addLayout(path_layout)

        self.chk_migrate = QCheckBox("Copy existing portfolio data to the new location")
        self.chk_migrate.setChecked(True)
        loc_layout.addWidget(self.chk_migrate)

        layout.addWidget(group_loc)

        # 2. Backup & Restore Section
        group_backup = QGroupBox("Manual Backup & Restore")
        group_backup.setStyleSheet("font-weight: 600; font-size: 13px;")
        bak_layout = QVBoxLayout(group_backup)
        bak_layout.setSpacing(10)

        bak_desc = QLabel(
            "Create an instant snapshot backup of your portfolio database to an external drive, "
            "or restore from a previous backup file."
        )
        bak_desc.setStyleSheet("color: #64748B; font-weight: normal; font-size: 12px;")
        bak_desc.setWordWrap(True)
        bak_layout.addWidget(bak_desc)

        bak_btn_layout = QHBoxLayout()
        self.btn_backup = QPushButton("Backup Database Now...")
        self.btn_backup.clicked.connect(self._on_backup_now)
        bak_btn_layout.addWidget(self.btn_backup)

        self.btn_restore = QPushButton("Restore from Backup...")
        self.btn_restore.clicked.connect(self._on_restore_now)
        bak_btn_layout.addWidget(self.btn_restore)

        bak_layout.addLayout(bak_btn_layout)
        layout.addWidget(group_backup)

        # Bottom Close button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

    def _on_browse_location(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Storage Folder (e.g. Google Drive)",
            str(Path.home()),
        )
        if not folder:
            return

        target_file = Path(folder) / "portfolio.db"
        confirm_msg = (
            f"Set database location to:\n{target_file}\n\n"
            f"Data migration: {'Enabled' if self.chk_migrate.isChecked() else 'Disabled'}"
        )
        reply = QMessageBox.question(
            self,
            "Confirm Database Location",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            try:
                set_custom_db_path(target_file, migrate_existing=self.chk_migrate.isChecked())
                self.txt_db_path.setText(str(target_file))
                self.db_reloaded.emit()
                QMessageBox.information(
                    self,
                    "Location Updated",
                    f"Portfolio database path updated successfully to:\n{target_file}",
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to set custom location:\n{e}")

    def _on_backup_now(self):
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Database Backup Snapshot",
            str(Path.home() / "portfolio_backup.db"),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not dest_path:
            return

        try:
            saved = backup_database(self.db_conn, dest_path)
            QMessageBox.information(self, "Backup Complete", f"Database successfully backed up to:\n{saved}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", f"Could not create backup:\n{e}")

    def _on_restore_now(self):
        src_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup Database to Restore",
            str(Path.home()),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not src_path:
            return

        confirm = QMessageBox.warning(
            self,
            "Confirm Restore",
            "Restoring will overwrite your current database with the selected backup snapshot.\n\nAre you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                restored = restore_database(src_path)
                self.db_reloaded.emit()
                QMessageBox.information(self, "Restore Complete", f"Database successfully restored from:\n{src_path}")
            except Exception as e:
                QMessageBox.critical(self, "Restore Failed", f"Could not restore database:\n{e}")

