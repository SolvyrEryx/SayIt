"""Tests for the Privacy & Data settings tab and its wiring."""

from unittest.mock import patch

import pytest

from src.sayit.core.settings import Settings
from src.sayit.ui.tabs.privacy_tab import (
    PrivacyTab,
    describe_enhancement_status,
    enhancement_sends_transcript_to_cloud,
)


class TestDisclosureLogic:
    def test_off_when_no_active_enhancement(self):
        s = Settings()
        assert describe_enhancement_status(s) == "Off"
        assert enhancement_sends_transcript_to_cloud(s) is False

    def test_cloud_when_active_and_remote_provider(self):
        s = Settings(active_enhancement_id="e1", llm_provider="openai")
        status = describe_enhancement_status(s)
        assert status.startswith("On — Cloud")
        assert "OpenAI" in status
        assert enhancement_sends_transcript_to_cloud(s) is True

    def test_local_when_active_and_ollama(self):
        s = Settings(active_enhancement_id="e1", llm_provider="ollama")
        status = describe_enhancement_status(s)
        assert status.startswith("On — Local")
        assert enhancement_sends_transcript_to_cloud(s) is False


class TestPrivacyTab:
    def test_toggle_reflects_history_setting(self, qtbot):
        s = Settings(history_enabled=True)
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert tab._history_checkbox.isChecked() is True

    def test_default_toggle_is_off(self, qtbot):
        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert tab._history_checkbox.isChecked() is False

    def test_toggle_updates_setting_on_save(self, qtbot):
        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        tab._history_checkbox.setChecked(True)
        tab.save_settings()
        assert s.history_enabled is True

    def test_status_label_reflects_cloud(self, qtbot):
        s = Settings(active_enhancement_id="e1", llm_provider="openai")
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert "Cloud" in tab._enhancement_status_label.text()
        assert "sent to this cloud provider" in tab._enhancement_detail_label.text()

    def test_status_label_reflects_off(self, qtbot):
        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert "Off" in tab._enhancement_status_label.text()
        assert "not sent anywhere" in tab._enhancement_detail_label.text()

    def test_clear_data_accessible_and_guarded(self, qtbot):
        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        assert tab._clear_data_btn.accessibleName() == "Clear data"

        # Cancel path: nothing scheduled.
        with (
            patch(
                "src.sayit.ui.tabs.privacy_tab.get_all_data_paths",
                return_value=["C:/x/settings.json"],
            ),
            patch(
                "src.sayit.ui.tabs.privacy_tab.QMessageBox.warning",
                return_value=None,
            ),
            patch(
                "src.sayit.ui.tabs.privacy_tab.schedule_cleanup_and_exit"
            ) as mock_sched,
        ):
            tab._on_clear_data_clicked()
            mock_sched.assert_not_called()

    def test_accessible_names_present(self, qtbot):
        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        assert tab._history_checkbox.accessibleName() == "Save transcript history"
        assert tab._enhancement_status_label.accessibleName()

    def test_history_control_is_animated_toggle(self, qtbot):
        from src.sayit.ui.widgets import AnimatedToggle

        s = Settings()
        tab = PrivacyTab(s)
        qtbot.addWidget(tab)
        assert isinstance(tab._history_checkbox, AnimatedToggle)
        # Still behaves like a boolean control for load/save.
        tab._history_checkbox.setChecked(True)
        tab.save_settings()
        assert s.history_enabled is True


class TestSettingsWindowPrivacyIntegration:
    def test_privacy_tab_present_and_persists(self, qtbot):
        from src.sayit.ui.main_window import SettingsWindow

        with patch("src.sayit.ui.main_window.get_settings") as mock_get:
            s = Settings()
            mock_get.return_value = s
            w = SettingsWindow()
            qtbot.addWidget(w)

            titles = [
                w._nav_list.item(i).text() for i in range(w._nav_list.count())
            ]
            assert "Privacy & Data" in titles

            # Toggle history on and save -> persists to the shared settings.
            w._privacy_tab._history_checkbox.setChecked(True)
            with patch.object(Settings, "save", autospec=True):
                w._save_settings()
            assert s.history_enabled is True
