"""Settings-UI tests for the assistant conversation-history toggle (WS A).

Verify the checkbox reflects the persisted value, round-trips through save,
stays independent of the transcript history_enabled setting, and that
clear-history removes only the conversation store file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sayit.core.settings.settings as st  # noqa: E402
from sayit.core.settings.settings import Settings  # noqa: E402
from sayit.core.conversation import ConversationEngine, ConversationStore  # noqa: E402
from sayit.ui.tabs.configuration_tab import ConfigurationTab  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _tab(settings):
    tab = ConfigurationTab(settings)
    return tab


def test_checkbox_default_off_reflects_setting(qtbot):
    _app()
    s = Settings()
    assert s.conversation_history_enabled is False
    tab = _tab(s)
    qtbot.addWidget(tab)
    tab.load_settings()
    assert tab._conversation_history_cb.isChecked() is False


def test_checkbox_reflects_enabled_setting(qtbot):
    _app()
    s = Settings()
    s.conversation_history_enabled = True
    tab = _tab(s)
    qtbot.addWidget(tab)
    tab.load_settings()
    assert tab._conversation_history_cb.isChecked() is True


def test_checkbox_persists_on_save(qtbot):
    _app()
    s = Settings()
    tab = _tab(s)
    qtbot.addWidget(tab)
    tab.load_settings()
    tab._conversation_history_cb.setChecked(True)
    tab.save_settings()
    assert s.conversation_history_enabled is True


def test_independent_of_transcript_history(qtbot):
    _app()
    s = Settings()
    tab = _tab(s)
    qtbot.addWidget(tab)
    tab.load_settings()
    # Enabling conversation history must NOT change transcript history_enabled.
    tab._conversation_history_cb.setChecked(True)
    tab.save_settings()
    assert s.conversation_history_enabled is True
    assert s.history_enabled is False  # untouched
    # And vice-versa: flipping transcript history does not change conversation.
    s.history_enabled = True
    tab.load_settings()
    assert tab._conversation_history_cb.isChecked() is True  # still independent


def test_round_trip_through_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(st, "_get_default_enhancements", lambda: [])
    s = Settings()
    s.conversation_history_enabled = True
    s.save()
    loaded = Settings.load()
    assert loaded.conversation_history_enabled is True
    assert loaded.history_enabled is False


def test_clear_history_removes_only_conversation_file(qtbot, tmp_path, monkeypatch):
    _app()
    # Point the conversation store at a temp dir and seed a file + a sibling
    # notes/settings file that must NOT be touched.
    import sayit.core.conversation.store as cs
    monkeypatch.setattr(cs, "_default_path", lambda: tmp_path / "conversation.json")
    store = ConversationStore(enabled=True, path=tmp_path / "conversation.json")
    o_engine = ConversationEngine()
    o_engine.handle_turn("Remind me tomorrow.")
    store.save(o_engine.state)
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    assert (tmp_path / "conversation.json").exists()

    s = Settings()
    tab = _tab(s)
    qtbot.addWidget(tab)
    # Patch the modal confirmation dialogs so the handler never blocks on user
    # input in a headless run (same convention as test_privacy_tab.py). Without
    # this, QMessageBox.information() opens a modal that waits forever.
    import sayit.ui.tabs.configuration_tab as cfg
    monkeypatch.setattr(cfg.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(cfg.QMessageBox, "warning", lambda *a, **k: None)
    tab._on_clear_conversation_history()

    assert not (tmp_path / "conversation.json").exists()  # removed
    assert (tmp_path / "notes.json").exists()              # untouched
    assert (tmp_path / "settings.json").exists()           # untouched
