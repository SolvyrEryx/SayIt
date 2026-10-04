"""Regression tests for model/hotkey persistence and settings reset."""
import json
from unittest.mock import patch

from src.sayit.core.settings import HotkeyConfig, Settings


def _disk_roundtrip(settings: Settings, config_dir):
    settings.save()
    assert (config_dir / "settings.json").exists()
    return Settings.load()


def test_non_default_model_persists_to_disk(tmp_path):
    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        settings = Settings(model_id="sherpa-onnx-whisper-small")
        restored = _disk_roundtrip(settings, tmp_path)

    assert restored.model_id == "sherpa-onnx-whisper-small"


def test_custom_hotkey_persists_to_disk(tmp_path):
    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        settings = Settings(hotkey=HotkeyConfig(modifiers=["alt", "shift"], key="r"))
        restored = _disk_roundtrip(settings, tmp_path)

    assert restored.hotkey.modifiers == ["alt", "shift"]
    assert restored.hotkey.key == "r"


def test_model_and_hotkey_persist_together(tmp_path):
    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        settings = Settings(
            model_id="sherpa-onnx-whisper-small",
            hotkey=HotkeyConfig(modifiers=["ctrl", "shift"], key="r"),
        )
        restored = _disk_roundtrip(settings, tmp_path)

    assert restored.model_id == "sherpa-onnx-whisper-small"
    assert restored.hotkey == HotkeyConfig(modifiers=["ctrl", "shift"], key="r")


def test_reset_restores_current_shipped_model_default():
    settings = Settings(
        model_id="sherpa-onnx-whisper-small",
        hotkey=HotkeyConfig(modifiers=["alt"], key="r"),
    )
    settings.reset_to_defaults()

    assert settings.model_id == Settings().model_id
    assert settings.hotkey == HotkeyConfig()


def test_reset_preserves_typed_hotkey():
    settings = Settings(hotkey=HotkeyConfig(modifiers=["alt"], key="r"))
    settings.reset_to_defaults()

    assert isinstance(settings.hotkey, HotkeyConfig)
    assert settings.hotkey.modifiers == ["ctrl"]
    assert settings.hotkey.key == "space"


def test_reset_can_be_saved_and_reloaded(tmp_path):
    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        settings = Settings(
            model_id="sherpa-onnx-whisper-small",
            hotkey=HotkeyConfig(modifiers=["alt"], key="r"),
        )
        settings.save()

        settings.reset_to_defaults()
        settings.save()

        restored = Settings.load()

    default = Settings()
    assert restored.model_id == default.model_id
    assert restored.hotkey == default.hotkey


def test_saved_json_contains_model_and_hotkey(tmp_path):
    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        settings = Settings(
            model_id="sherpa-onnx-whisper-small",
            hotkey=HotkeyConfig(modifiers=["ctrl", "alt"], key="k"),
        )
        settings.save()

        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))

    assert data["model_id"] == "sherpa-onnx-whisper-small"
    assert data["hotkey"] == {"modifiers": ["ctrl", "alt"], "key": "k"}


def test_loads_legacy_nested_hotkey_as_typed_model(tmp_path):
    config = {
        "model_id": "sherpa-onnx-whisper-small",
        "hotkey": {"modifiers": ["shift"], "key": "f9"},
    }
    (tmp_path / "settings.json").write_text(json.dumps(config), encoding="utf-8")

    with patch("src.sayit.core.settings.settings.get_config_dir", return_value=tmp_path):
        restored = Settings.load()

    assert restored.model_id == "sherpa-onnx-whisper-small"
    assert isinstance(restored.hotkey, HotkeyConfig)
    assert restored.hotkey.modifiers == ["shift"]
    assert restored.hotkey.key == "f9"
