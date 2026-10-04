"""Tests for the opt-in Whisper Small CPU-thread setting (bounded {4,6,8}).

Covers: default 4, allowed 6/8, invalid/missing fall back to 4 (backward
compat), the setting does NOT alter Parakeet (transducer never receives it),
the backend receives the correct num_threads for whisper, engine threading, and
the Advanced/Performance UI control. Production defaults are not changed.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sayit.core.asr import speech_mode as SM
from sayit.core.asr.backends import SherpaOnnxBackend
from sayit.core.asr.transcriber import TranscriptionEngine
from sayit.core.settings import Settings
from sayit.core.settings.settings import (
    DEFAULT_WHISPER_CPU_THREADS,
    WHISPER_CPU_THREAD_CHOICES,
)


class TestSettingField:
    def test_default_is_4(self):
        assert DEFAULT_WHISPER_CPU_THREADS == 4
        assert Settings().whisper_small_cpu_threads == 4

    def test_allowed_set_is_4_6_8(self):
        assert tuple(WHISPER_CPU_THREAD_CHOICES) == (4, 6, 8)

    @pytest.mark.parametrize("value", [4, 6, 8])
    def test_allowed_values_accepted(self, value):
        assert Settings(whisper_small_cpu_threads=value).whisper_small_cpu_threads == value

    @pytest.mark.parametrize("value", [1, 2, 3, 5, 7, 12, 100, 0, -4])
    def test_invalid_int_coerced_to_4_via_constructor(self, value):
        assert Settings(whisper_small_cpu_threads=value).whisper_small_cpu_threads == 4

    def test_not_coupled_to_experimental_flag(self):
        s = Settings(whisper_small_cpu_threads=8)
        assert s.intelligence_experimental_enabled is False
        assert s.whisper_small_cpu_threads == 8


class TestLoadBackwardCompat:
    def test_missing_key_defaults_to_4(self):
        s = Settings._load_with_fallbacks({"model_id": "x"})
        assert s.whisper_small_cpu_threads == 4

    @pytest.mark.parametrize("value,expected", [(4, 4), (6, 6), (8, 8)])
    def test_valid_values_survive_load(self, value, expected, tmp_path, monkeypatch):
        self._roundtrip_disk(value, expected, tmp_path, monkeypatch)

    @pytest.mark.parametrize("value", [5, 7, 12, 1, 999])
    def test_invalid_int_clamped_on_load(self, value, tmp_path, monkeypatch):
        self._roundtrip_disk(value, 4, tmp_path, monkeypatch)

    @pytest.mark.parametrize("value", ["x", None])
    def test_invalid_type_clamped_on_load(self, value, tmp_path, monkeypatch):
        self._roundtrip_disk(value, 4, tmp_path, monkeypatch)

    def test_missing_from_disk_defaults_to_4(self, tmp_path, monkeypatch):
        import json
        from sayit.core.settings import settings as S

        cfg = tmp_path / "settings.json"
        cfg.write_text(json.dumps({"model_id": SM.FAST_MODEL_ID}), encoding="utf-8")
        monkeypatch.setattr(S, "get_config_dir", lambda: tmp_path)
        assert Settings.load().whisper_small_cpu_threads == 4

    @staticmethod
    def _roundtrip_disk(value, expected, tmp_path, monkeypatch):
        import json
        from sayit.core.settings import settings as S

        cfg = tmp_path / "settings.json"
        cfg.write_text(json.dumps({"whisper_small_cpu_threads": value}), encoding="utf-8")
        monkeypatch.setattr(S, "get_config_dir", lambda: tmp_path)
        assert Settings.load().whisper_small_cpu_threads == expected


class TestBackendRouting:
    """The thread count reaches the whisper loader; the transducer loader never
    receives it (Parakeet is unaffected)."""

    def _mock_model_dir(self, monkeypatch):
        # These routing tests exercise model-type/thread dispatch, not model
        # download/caching. Keep the real backend cache check intact in production
        # while isolating it here.
        monkeypatch.setattr(os.path, "isdir", lambda path: True)

    def test_whisper_receives_num_threads_and_transducer_does_not(self, monkeypatch):
        self._mock_model_dir(monkeypatch)
        captured = {}

        def fake_w(self, so, path, num_threads=4):
            captured["whisper"] = num_threads
            self._recognizer = object()

        def fake_t(self, so, path):
            captured["transducer"] = "called_without_threads"
            self._recognizer = object()

        monkeypatch.setattr(SherpaOnnxBackend, "_load_whisper_model", fake_w)
        monkeypatch.setattr(SherpaOnnxBackend, "_load_transducer_model", fake_t)

        SherpaOnnxBackend().load(SM.HIGHER_ACCURACY_MODEL_ID, whisper_num_threads=8)
        assert captured["whisper"] == 8

        SherpaOnnxBackend().load(SM.FAST_MODEL_ID, whisper_num_threads=8)
        assert captured["transducer"] == "called_without_threads"

    def test_backend_load_default_whisper_threads_is_4(self, monkeypatch):
        self._mock_model_dir(monkeypatch)
        captured = {}

        def fake_w(self, so, path, num_threads=4):
            captured["whisper"] = num_threads
            self._recognizer = object()

        monkeypatch.setattr(SherpaOnnxBackend, "_load_whisper_model", fake_w)
        SherpaOnnxBackend().load(SM.HIGHER_ACCURACY_MODEL_ID)
        assert captured["whisper"] == 4


class TestEngineThreading:
    def test_engine_default_threads_is_4(self):
        assert TranscriptionEngine(model_name=SM.HIGHER_ACCURACY_MODEL_ID)._whisper_num_threads == 4

    def test_engine_passes_threads_to_backend(self, monkeypatch):
        captured = {}

        def fake_load(self, model_path, on_progress=None, whisper_num_threads=4):
            captured["threads"] = whisper_num_threads
            self._recognizer = object()

        monkeypatch.setattr(SherpaOnnxBackend, "load", fake_load)
        eng = TranscriptionEngine(model_name=SM.HIGHER_ACCURACY_MODEL_ID, whisper_num_threads=8)
        eng.load_model()
        assert captured["threads"] == 8


class TestParakeetUnaffected:
    def test_parakeet_default_model_and_threads_setting_independent(self):
        s = Settings()
        assert s.model_id == SM.FAST_MODEL_ID
        assert s.whisper_small_cpu_threads == 4


class TestUISelector:
    def _tab(self):
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        from sayit.ui.tabs.configuration_tab import ConfigurationTab
        QApplication.instance() or QApplication([])
        return ConfigurationTab(Settings())

    def test_has_three_radios(self):
        tab = self._tab()
        assert sorted(tab._whisper_threads_radios.keys()) == [4, 6, 8]

    def test_default_checked_is_4(self):
        tab = self._tab()
        tab.load_settings()
        assert tab._whisper_threads_radios[4].isChecked()

    def test_save_persists_selected_value(self):
        tab = self._tab()
        tab.load_settings()
        tab._whisper_threads_radios[8].setChecked(True)
        assert tab.save_settings() is True
        assert tab._settings.whisper_small_cpu_threads == 8

    def test_load_reflects_persisted_value(self):
        from PySide6.QtWidgets import QApplication
        from sayit.ui.tabs.configuration_tab import ConfigurationTab
        tab = ConfigurationTab(Settings(whisper_small_cpu_threads=6))
        tab.load_settings()
        assert tab._whisper_threads_radios[6].isChecked()
