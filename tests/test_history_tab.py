"""Tests for the History tab honest empty state when history is disabled."""

from unittest.mock import patch

from src.sayit.core.settings import Settings
from src.sayit.ui.tabs.history_tab import HistoryTab


def _make_tab(qtbot):
    tab = HistoryTab()
    qtbot.addWidget(tab)
    # Stop the periodic timer so the test controls refreshes.
    tab.stop_refresh_timer()
    return tab


def test_history_off_shows_status(qtbot):
    with (
        patch(
            "src.sayit.ui.tabs.history_tab.get_settings",
            return_value=Settings(history_enabled=False),
        ),
        patch(
            "src.sayit.ui.tabs.history_tab.load_history", return_value=[]
        ),
    ):
        tab = _make_tab(qtbot)
        tab.refresh_history()
        assert tab._status_label.isHidden() is False
        assert "off" in tab._status_label.text().lower()


def test_history_on_hides_status(qtbot):
    with (
        patch(
            "src.sayit.ui.tabs.history_tab.get_settings",
            return_value=Settings(history_enabled=True),
        ),
        patch(
            "src.sayit.ui.tabs.history_tab.load_history", return_value=[]
        ),
    ):
        tab = _make_tab(qtbot)
        tab.refresh_history()
        assert tab._status_label.isHidden() is True
