"""Regression tests for language-aware startup fallback.

Release-gate guarantee: a Hindi/Kannada dictation language must NEVER silently
fall back to the English-only Parakeet model when its model fails to load.
"""

from src.sayit.core.asr.language_routing import resolve_fallback_model
from src.sayit.core.settings.settings import FALLBACK_MODEL_ID

PARAKEET_EN = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"


class TestLanguageAwareFallback:
    def test_english_falls_back_to_english_model(self):
        # A failed English fp16 load may fall back to the English int8 model.
        fb = resolve_fallback_model(
            "en",
            failed_model_id="sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16",
            english_fallback_id=FALLBACK_MODEL_ID,
        )
        assert fb == FALLBACK_MODEL_ID

    def test_hindi_never_falls_back_to_english(self):
        # Hindi model failed; there is no OTHER Hindi model registered, so the
        # resolver must return None rather than the English Parakeet model.
        fb = resolve_fallback_model(
            "hi",
            failed_model_id="indicconformer-hi-int8",
            english_fallback_id=FALLBACK_MODEL_ID,
        )
        assert fb != FALLBACK_MODEL_ID
        assert fb != PARAKEET_EN
        assert fb is None  # no cross-language fallback

    def test_kannada_never_falls_back_to_english(self):
        fb = resolve_fallback_model(
            "kn",
            failed_model_id="indicconformer-kn-int8",
            english_fallback_id=FALLBACK_MODEL_ID,
        )
        assert fb != FALLBACK_MODEL_ID
        assert fb != PARAKEET_EN
        assert fb is None

    def test_english_fallback_not_itself(self):
        # If the English fallback is the model that just failed, don't loop.
        fb = resolve_fallback_model(
            "en",
            failed_model_id=FALLBACK_MODEL_ID,
            english_fallback_id=FALLBACK_MODEL_ID,
        )
        assert fb is None
