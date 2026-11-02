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


def pytest_sessionfinish(session, exitstatus):
    """Gracefully terminate process to prevent Python 3.15 / Qt C++ destructor race."""
    import os
    if exitstatus == 0:
        os._exit(0)


