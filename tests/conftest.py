"""Shared test fixtures for Portfolio Tracker pytest suite."""

import sys
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped offscreen QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv + ["-platform", "offscreen"])
    return app


@pytest.fixture(autouse=True)
def clean_qt_events(qapp):
    """Ensure all pending Qt deleteLater and paint events are processed between tests."""
    yield
    for widget in qapp.topLevelWidgets():
        widget.close()
    qapp.processEvents()
    qapp.sendPostedEvents()

