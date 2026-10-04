"""Regression tests for hotkey parsing and first-use ASR model downloads."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit

from src.sayit.core.asr import transcriber as transcriber_module
from src.sayit.core.input import hotkey as hotkey_module
from src.sayit.core.settings import HotkeyConfig, Settings
from src.sayit.ui.tabs.configuration_tab import ConfigurationTab


def test_configuration_hotkey_parses_ctrl_space(qtbot):
    edit = QKeySequenceEdit()
    qtbot.addWidget(edit)
    edit.setKeySequence(QKeySequence("Ctrl+Space"))

    tab = ConfigurationTab.__new__(ConfigurationTab)
    tab._hotkey_edit = edit

    result = tab._parse_key_sequence()

    assert result == HotkeyConfig(modifiers=["ctrl"], key="space")


def test_configuration_hotkey_falls_back_when_qt_returns_no_modifier(qtbot):
    edit = QKeySequenceEdit()
    qtbot.addWidget(edit)
    edit.setKeySequence(QKeySequence("F9"))

    tab = ConfigurationTab.__new__(ConfigurationTab)
    tab._hotkey_edit = edit

    result = tab._parse_key_sequence()

    assert result == HotkeyConfig()



def test_hotkey_listener_re_registers_new_config_without_stale_listener():
    class FakeImpl:
        def __init__(self):
            self.is_running = True
            self.calls = []
            self._pressed_keys = {"stale"}

        def stop(self):
            self.calls.append("stop")
            self.is_running = False
            self._pressed_keys.clear()

        def update_config(self, trigger_key, modifiers):
            self.calls.append(("update", trigger_key, modifiers))

        def start(self):
            self.calls.append("start")
            self.is_running = True

    listener = hotkey_module.HotkeyListener.__new__(hotkey_module.HotkeyListener)
    listener._is_hotkey_active = False
    listener._impl = FakeImpl()
    listener._trigger_key = "space"
    listener._required_modifier_types = {"ctrl"}

    new_settings = Settings(
        hotkey=HotkeyConfig(modifiers=["alt", "shift"], key="r")
    )
    listener.update_settings(new_settings)

    assert listener._trigger_key == "r"
    assert listener._required_modifier_types == {"alt", "shift"}
    assert listener._impl._pressed_keys == set()
    assert listener._impl.calls == [
        "stop",
        ("update", "r", {"alt", "shift"}),
        "start",
    ]


def test_hotkey_listener_uses_persisted_config_on_startup(monkeypatch):
    persisted = Settings(
        hotkey=HotkeyConfig(modifiers=["alt"], key="r")
    )
    monkeypatch.setattr(hotkey_module, "get_settings", lambda: persisted)

    class FakeImpl:
        def __init__(self, listener):
            self.listener = listener

        @property
        def is_running(self):
            return False

        def update_config(self, *args):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(hotkey_module, "_PynputHotkeyListenerImpl", FakeImpl)

    listener = hotkey_module.HotkeyListener()

    assert listener._required_modifier_types == {"alt"}
    assert listener._trigger_key == "r"


def test_engine_downloads_missing_registry_model(monkeypatch):
    events = []
    progress = []
    download_calls = []

    model = SimpleNamespace(
        id="sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
        name="Parakeet TDT v2 0.6B (Int8)",
        type="transducer",
    )

    availability = iter([False, True])
    monkeypatch.setattr(
        transcriber_module,
        "get_model_by_id",
        lambda model_id: model if model_id == model.id else None,
    )
    monkeypatch.setattr(
        transcriber_module,
        "is_model_downloaded",
        lambda model_id: next(availability),
    )

    class FakeDownloader:
        def __init__(self):
            self.cancelled = False

        def download(self, model_id, on_progress=None, on_status=None):
            download_calls.append(model_id)
            on_status("Downloading...")
            on_progress(50, 100)
            on_progress(100, 100)
            return True

        def cancel(self):
            self.cancelled = True

    class FakeBackend:
        device = "cpu"
        is_loaded = False

        def load(self, **kwargs):
            return None

    monkeypatch.setattr(transcriber_module, "ModelDownloader", FakeDownloader)
    monkeypatch.setattr(transcriber_module, "SherpaOnnxBackend", FakeBackend)

    engine = transcriber_module.TranscriptionEngine(
        model_name=model.id,
        on_state_change=lambda state, message: events.append((state, message)),
        on_download_progress=lambda value: progress.append(value),
    )

    assert engine.load_model() is True
    assert download_calls == [model.id]
    assert progress == [0.5, 1.0]
    assert any(state.name == "DOWNLOADING" for state, _ in events)
    assert events[-1][0].name == "READY"


def test_engine_can_cancel_active_model_download(monkeypatch):
    downloader = MagicMock()
    monkeypatch.setattr(transcriber_module, "ModelDownloader", lambda: downloader)

    engine = transcriber_module.TranscriptionEngine()
    engine._model_downloader = downloader

    engine.cancel_model_download()

    downloader.cancel.assert_called_once()
