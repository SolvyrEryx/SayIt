"""Pytest configuration for Qt-based tests."""

import os

import pytest
from PySide6.QtWidgets import QApplication

# Make UI motion instant/deterministic in tests so assertions don't depend on
# animation timing. Production behavior is unaffected.
os.environ.setdefault("SAYIT_REDUCED_MOTION", "1")


@pytest.fixture(autouse=True)
def cleanup_qt_objects(qtbot, request):
    yield
    app = QApplication.instance()
    if app:
        app.processEvents()
