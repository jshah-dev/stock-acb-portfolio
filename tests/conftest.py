"""Shared test fixtures for Portfolio Tracker pytest suite."""

import os
import sys

# Default to offscreen platform for headless environments (e.g. CI/CD)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped offscreen QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv + ["-platform", "offscreen"])
        from PySide6.QtGui import QFont
        from portfolio_tracker.ui.styles import SYSTEM_FONT
        app.setFont(QFont(SYSTEM_FONT, 13))
    return app


@pytest.fixture(autouse=True)
def clean_qt_events(qapp):
    """Ensure all pending Qt deleteLater and paint events are processed between tests."""
    yield
    for widget in qapp.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents()



