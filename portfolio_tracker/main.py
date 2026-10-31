"""Application entry point and Qt event loop lifecycle management."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from portfolio_tracker.db import init_db
from portfolio_tracker.ui.main_window import MainWindow
from portfolio_tracker.ui.styles import MAIN_STYLESHEET, SYSTEM_FONT


def main():
    """Bootstrap and launch the Portfolio Tracker desktop application."""
    # Hardware acceleration crash-guard: support fallback on older Windows PCs
    if sys.platform == "win32":
        # Disable GPU compositing if user has low-end drivers to prevent Chromium crashes
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

    # Enable OpenGL context sharing for WebEngine
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("StockACBPortfolioTracker")
    app.setOrganizationName("JShah")

    # Set platform-native font before stylesheet to avoid font alias search delay
    app.setFont(QFont(SYSTEM_FONT, 13))

    # Apply global modern Tailwind Slate stylesheet
    app.setStyleSheet(MAIN_STYLESHEET)

    # Initialize SQLite database
    db_conn = init_db()

    # Create main window
    window = MainWindow(db_conn)
    window.show()

    # Clean shutdown connection
    def on_about_to_quit():
        try:
            db_conn.close()
        except Exception:
            pass

    app.aboutToQuit.connect(on_about_to_quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

