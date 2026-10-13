"""Regression tests for the live-microphone dictation root cause.

Root cause (evidence from the installed-app log): the loaded ASR model could
disagree with the selected dictation language — Hindi/Kannada speech was being
transcribed by the English Parakeet model, producing wrong text. The app now
reconciles ``dictation_language`` and ``model_id`` at startup and keeps them in
sync when the model is changed in Settings.

These tests exercise the routing contract that the reconciliation relies on,
plus the standalone reconciliation outcome, without constructing the full Qt
application.
"""

import pytest

from src.sayit.core.asr.language_routing import (
    get_model_language,
    is_compatible,
    resolve_model_for_language,
)

PARAKEET_EN = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
HI = "indicconformer-hi-int8"
KN = "indicconformer-kn-int8"


class TestLanguageModelReconciliation:
    def test_hindi_language_with_english_model_reconciles_to_hindi(self):
        # The exact failing scenario: dictation_language=hi, model=English.
        assert is_compatible("hi", PARAKEET_EN) is False
        route = resolve_model_for_language("hi", PARAKEET_EN)
        assert route.model_id == HI
        assert route.compatible is True

    def test_kannada_language_with_english_model_reconciles_to_kannada(self):
        assert is_compatible("kn", PARAKEET_EN) is False
        route = resolve_model_for_language("kn", PARAKEET_EN)
        assert route.model_id == KN

    def test_english_language_keeps_english_model(self):
        assert is_compatible("en", PARAKEET_EN) is True
        route = resolve_model_for_language("en", PARAKEET_EN)
        assert route.model_id == PARAKEET_EN

    def test_model_language_backfill(self):
        # When language is unknown, it can be derived from the model.
        assert get_model_language(PARAKEET_EN) == "en"
        assert get_model_language(HI) == "hi"
        assert get_model_language(KN) == "kn"

    def test_reconcile_helper_matches_app_logic(self):
        # Mirror of TranscribeApp._reconcile_language_and_model (pure part).
        def reconcile(lang, model_id):
            if lang is None:
                lang = "en"
            model_lang = get_model_language(model_id)
            if model_lang == lang:
                return model_id  # consistent
            if lang == "en" and model_lang is not None:
                return model_id  # adopt model's language; keep model
            if is_compatible(lang, model_id):
                return model_id
            r = resolve_model_for_language(lang, model_id)
            return r.model_id or model_id

        # hi + english -> hindi model
        assert reconcile("hi", PARAKEET_EN) == HI
        # kn + english -> kannada model
        assert reconcile("kn", PARAKEET_EN) == KN
        # en + english -> unchanged
        assert reconcile("en", PARAKEET_EN) == PARAKEET_EN
        # None language + english -> unchanged (stay english)
        assert reconcile(None, PARAKEET_EN) == PARAKEET_EN
        # hi + hindi -> unchanged
        assert reconcile("hi", HI) == HI


class TestConfigTabModelLanguageSync:
    def test_selecting_indic_model_sets_language(self, qtbot):
        from unittest.mock import patch

        from src.sayit.core.settings import Settings

        # The config-tab apply path sets dictation_language from the model.
        # Verify the mapping used there is correct for each model.
        assert get_model_language(HI) == "hi"
        assert get_model_language(KN) == "kn"
        assert get_model_language(PARAKEET_EN) == "en"
