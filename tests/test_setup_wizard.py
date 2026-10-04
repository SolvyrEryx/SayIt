"""Tests for the first-run setup wizard (no ASR model required)."""

from unittest.mock import patch

import pytest

from src.sayit.core.settings import HotkeyConfig
from src.sayit.ui.setup_wizard import (
    CompletePage,
    HotkeyPage,
    ModelSelectionPage,
    SetupWizard,
    TryItPage,
)


@pytest.fixture
def wizard(qtbot):
    # Avoid writing real settings/devices during construction.
    with patch(
        "src.sayit.ui.setup_wizard.AudioRecorder.list_devices", return_value=[]
    ):
        w = SetupWizard()
        qtbot.addWidget(w)
        yield w


class TestWizardFlow:
    def test_page_order(self, wizard):
        titles = [wizard.page(i).title() for i in wizard.pageIds()]
        assert titles == [
            "Welcome to SayIt",
            "Microphone",
            "Speech Model",
            "Push-to-Talk Hotkey",
            "Try Your First Dictation",
            "Setup Complete",
        ]

    def test_model_step_is_non_blocking(self, wizard):
        # The wizard must be completable without downloading a model.
        assert wizard._model_page.isComplete() is True


class TestModelHonesty:
    def test_model_not_ready_when_not_downloaded(self, qtbot):
        with patch(
            "src.sayit.ui.setup_wizard.is_model_downloaded", return_value=False
        ):
            page = ModelSelectionPage()
            qtbot.addWidget(page)
            assert page.is_model_ready() is False

    def test_model_ready_when_downloaded(self, qtbot):
        with patch(
            "src.sayit.ui.setup_wizard.is_model_downloaded", return_value=True
        ):
            page = ModelSelectionPage()
            qtbot.addWidget(page)
            assert page.is_model_ready() is True


class TestTryItHonesty:
    def test_tryit_model_unavailable_text_no_fake_transcript(self, qtbot):
        model_page = ModelSelectionPage()
        hotkey_page = HotkeyPage()
        qtbot.addWidget(model_page)
        qtbot.addWidget(hotkey_page)
        with patch.object(model_page, "is_model_ready", return_value=False):
            page = TryItPage(model_page, hotkey_page)
            qtbot.addWidget(page)
            page.initializePage()
            text = page._body.text().lower()
            assert "isn't installed" in text or "not installed" in text
            # Must not fabricate a success/transcript.
            assert "test successful" not in text
            assert "simulated" in text  # explicitly states nothing is simulated

    def test_tryit_model_ready_text(self, qtbot):
        model_page = ModelSelectionPage()
        hotkey_page = HotkeyPage()
        qtbot.addWidget(model_page)
        qtbot.addWidget(hotkey_page)
        with patch.object(model_page, "is_model_ready", return_value=True):
            page = TryItPage(model_page, hotkey_page)
            qtbot.addWidget(page)
            page.initializePage()
            text = page._body.text().lower()
            assert "ready to dictate" in text


class TestCompletionHonesty:
    def test_complete_lists_remaining_when_model_missing(self, qtbot):
        model_page = ModelSelectionPage()
        qtbot.addWidget(model_page)
        with patch.object(model_page, "is_model_ready", return_value=False):
            page = CompletePage(model_page)
            qtbot.addWidget(page)
            page.initializePage()
            text = page._summary.text().lower()
            assert "remaining" in text
            assert "model" in text

    def test_complete_all_ready_when_model_installed(self, qtbot):
        model_page = ModelSelectionPage()
        qtbot.addWidget(model_page)
        with patch.object(model_page, "is_model_ready", return_value=True):
            page = CompletePage(model_page)
            qtbot.addWidget(page)
            page.initializePage()
            text = page._summary.text().lower()
            assert "remaining" not in text
            assert "ready" in text


class TestHotkeyParsing:
    def test_valid_combo(self, qtbot):
        from PySide6.QtGui import QKeySequence

        page = HotkeyPage()
        qtbot.addWidget(page)
        page._hotkey_edit.setKeySequence(QKeySequence("Ctrl+Shift+K"))
        cfg = page.get_hotkey_config()
        assert "ctrl" in cfg.modifiers
        assert "shift" in cfg.modifiers
        assert cfg.key == "k"

    def test_modifierless_falls_back_to_default(self, qtbot):
        from PySide6.QtGui import QKeySequence

        page = HotkeyPage()
        qtbot.addWidget(page)
        page._hotkey_edit.setKeySequence(QKeySequence("A"))
        cfg = page.get_hotkey_config()
        # Must not persist a risky modifier-less push-to-talk key.
        assert cfg.modifiers == HotkeyConfig().modifiers
        assert cfg.key == HotkeyConfig().key


class TestPersistence:
    def test_accept_persists_settings(self, qtbot):
        from src.sayit.core.settings import Settings

        with patch(
            "src.sayit.ui.setup_wizard.AudioRecorder.list_devices", return_value=[]
        ):
            w = SetupWizard()
            qtbot.addWidget(w)
            with patch.object(Settings, "save", autospec=True) as mock_save:
                w.accept()
            mock_save.assert_called_once()
            assert w._settings.first_run_complete is True
