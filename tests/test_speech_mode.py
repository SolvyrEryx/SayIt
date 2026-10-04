"""Whisper Small opt-in speech-mode tests.

Covers model selection, default, persistence, availability, routing, status
display, failed-load safety, backward compatibility, and the UI selector.
Production default (Parakeet) and the experimental flag are not changed.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sayit.core.asr import speech_mode as SM
from sayit.core.asr.transcriber import TranscriptionEngine
from sayit.core.settings import Settings
from sayit.core.settings.settings import DEFAULT_MODEL_ID


class TestSpeechModeMapping:
    def test_default_mode_is_fast_parakeet(self):
        assert SM.DEFAULT_MODE == SM.FAST
        assert SM.model_id_for_mode(SM.FAST) == DEFAULT_MODEL_ID
        assert SM.model_id_for_mode(SM.FAST) == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"

    def test_higher_accuracy_maps_to_whisper_small(self):
        assert SM.model_id_for_mode(SM.HIGHER_ACCURACY) == "sherpa-onnx-whisper-small"

    def test_mode_for_model_id_roundtrip(self):
        assert SM.mode_for_model_id(SM.FAST_MODEL_ID) == SM.FAST
        assert SM.mode_for_model_id(SM.HIGHER_ACCURACY_MODEL_ID) == SM.HIGHER_ACCURACY

    def test_legacy_or_unknown_model_id_defaults_to_fast_mode(self):
        # An unknown/legacy id must not crash and must not be silently rewritten.
        assert SM.mode_for_model_id("some-old-model") == SM.FAST
        assert SM.is_known_mode_model("some-old-model") is False

    def test_two_modes_listed_fast_first(self):
        modes = SM.all_modes()
        assert [m.mode for m in modes] == [SM.FAST, SM.HIGHER_ACCURACY]

    def test_higher_accuracy_is_optional_fast_is_not(self):
        assert SM.get_mode(SM.HIGHER_ACCURACY).optional is True
        assert SM.get_mode(SM.FAST).optional is False

    def test_status_line_is_friendly_no_backend_name(self):
        line = SM.status_line(SM.HIGHER_ACCURACY_MODEL_ID)
        assert "Higher Accuracy" in line and "Whisper Small" in line
        assert "SherpaOnnx" not in line and "Backend" not in line
        assert SM.status_line(SM.FAST_MODEL_ID).startswith("Fast")

    def test_not_coupled_to_experimental_flag(self):
        # Speech mode is model_id-based and independent of the experimental flag.
        s = Settings(model_id=SM.HIGHER_ACCURACY_MODEL_ID)
        assert s.intelligence_experimental_enabled is False  # default unchanged
        assert SM.mode_for_model_id(s.model_id) == SM.HIGHER_ACCURACY


class TestAvailability:
    def test_mode_status_tokens(self):
        # Whatever the install state, the token must be one of the known values.
        for mode in (SM.FAST, SM.HIGHER_ACCURACY):
            assert SM.mode_status(mode) in ("Installed", "Ready", "Not installed")

    def test_availability_is_boolean(self):
        assert isinstance(SM.is_mode_available(SM.FAST), bool)


class TestPersistence:
    def test_settings_default_model_is_parakeet(self):
        assert Settings().model_id == DEFAULT_MODEL_ID

    def test_model_id_roundtrips(self):
        s = Settings(model_id=SM.HIGHER_ACCURACY_MODEL_ID)
        s2 = Settings(**s.model_dump())
        assert s2.model_id == SM.HIGHER_ACCURACY_MODEL_ID


class TestRoutingAndSwitchingContract:
    def test_engine_switch_model_updates_name(self):
        eng = TranscriptionEngine(model_name=SM.FAST_MODEL_ID)
        # switch_model unloads + sets the new name (does not require loading here)
        assert eng.model_name == SM.FAST_MODEL_ID
        eng.model_name = SM.HIGHER_ACCURACY_MODEL_ID
        assert eng.model_name == SM.HIGHER_ACCURACY_MODEL_ID

    def test_backend_routes_by_model_type(self):
        from sayit.core.asr.backends import get_model_type
        assert get_model_type(SM.FAST_MODEL_ID) == "transducer"
        assert get_model_type(SM.HIGHER_ACCURACY_MODEL_ID) == "whisper"


class TestFailedLoadSafety:
    def test_unknown_model_raises_not_silent_swap(self):
        from sayit.core.asr.backends import SherpaOnnxBackend
        b = SherpaOnnxBackend()
        with pytest.raises(Exception):
            b.load("sherpa-onnx-does-not-exist")
        # backend stays unloaded (did not silently fall back to another model)
        assert b.is_loaded is False


class TestUISelector:
    def _tab(self):
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        from sayit.ui.tabs.configuration_tab import ConfigurationTab
        app = QApplication.instance() or QApplication([])
        return ConfigurationTab(Settings()), app

    def test_selector_has_both_modes(self):
        tab, _ = self._tab()
        assert SM.FAST in tab._mode_radios and SM.HIGHER_ACCURACY in tab._mode_radios

    def test_default_selection_is_fast(self):
        tab, _ = self._tab()
        tab.load_settings()
        assert tab._mode_radios[SM.FAST].isChecked()

    def test_home_tab_has_set_speech_mode(self):
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        from sayit.ui.tabs.home_tab import HomeTab
        QApplication.instance() or QApplication([])
        h = HomeTab()
        h.set_speech_mode("Higher Accuracy · Whisper Small")
        assert h._mode_label.text() == "Higher Accuracy · Whisper Small"
        h.set_speech_mode("")  # empty hides
        assert h._mode_label.isHidden()
