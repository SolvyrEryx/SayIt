"""Tests for script-safe correction and dictation-language persistence."""

import pytest

from src.sayit.core.transcript_processor.script_utils import (
    contains_devanagari,
    contains_kannada,
    is_predominantly_non_latin,
    non_latin_ratio,
)
from src.sayit.core.transcript_processor.technical_corrector import correct_transcript


class TestScriptDetection:
    def test_english_is_latin(self):
        assert non_latin_ratio("deploy to production") == 0.0
        assert is_predominantly_non_latin("deploy to production") is False

    def test_hindi_devanagari(self):
        hi = "मैंने कोड लिखा"
        assert contains_devanagari(hi)
        assert non_latin_ratio(hi) == 1.0
        assert is_predominantly_non_latin(hi)

    def test_kannada(self):
        kn = "ನಾನು ಕೋಡ್ ಬರೆದಿದ್ದೇನೆ"
        assert contains_kannada(kn)
        assert non_latin_ratio(kn) == 1.0
        assert is_predominantly_non_latin(kn)

    def test_codeswitch_with_indic_abstains(self):
        # Even a mostly-English phrase with real Devanagari content abstains at
        # the conservative 0.2 threshold.
        assert is_predominantly_non_latin("deploy करें")


class TestScriptSafeCorrection:
    def test_english_still_corrected(self):
        r = correct_transcript("i pushed to git hub")
        assert "GitHub" in r.text

    def test_hindi_untouched(self):
        hi = "मैंने गिट हब पर कोड डाला"
        r = correct_transcript(hi)
        assert r.text == hi  # no corruption, exact passthrough

    def test_kannada_untouched(self):
        kn = "ನಾನು ಕೋಡ್ ಅನ್ನು ಪುಶ್ ಮಾಡಿದೆ"
        r = correct_transcript(kn)
        assert r.text == kn

    def test_intelligence_pipeline_abstains_non_latin(self):
        from src.sayit.core.asr.intelligence_pipeline import IntelligencePipeline

        pipe = IntelligencePipeline()
        hi = "मैंने कोड लिखा"
        res = pipe.process(hi)
        assert res.text == hi
        assert res.changed is False
        assert res.reason == "non_latin_script"


class TestDictationLanguagePersistence:
    def test_default_language_is_english(self):
        from src.sayit.core.settings.settings import Settings

        assert Settings().dictation_language == "en"

    def test_supported_languages_accepted(self):
        from src.sayit.core.settings.settings import Settings

        for lang in ("en", "hi", "kn"):
            s = Settings(dictation_language=lang)
            assert s.dictation_language == lang

    def test_invalid_language_falls_back_to_english(self):
        from src.sayit.core.settings.settings import Settings

        s = Settings(dictation_language="zz")
        assert s.dictation_language == "en"

    def test_language_round_trips_through_json(self, tmp_path, monkeypatch):
        from src.sayit.core.settings import settings as settings_mod

        monkeypatch.setattr(settings_mod, "get_config_dir", lambda: tmp_path)
        s = settings_mod.Settings()
        s.dictation_language = "hi"
        s.save()
        loaded = settings_mod.Settings.load()
        assert loaded.dictation_language == "hi"


class TestOnboardingLanguagePage:
    def test_language_page_offers_three_languages(self, qtbot):
        from src.sayit.ui.setup_wizard import LanguagePage

        page = LanguagePage()
        qtbot.addWidget(page)
        codes = {
            page._language_combo.itemData(i)
            for i in range(page._language_combo.count())
        }
        assert codes == {"en", "hi", "kn"}
        # English pre-selected by default.
        assert page.get_selected_language() == "en"

    def test_model_page_language_filter_excludes_english_for_hindi(self, qtbot):
        from src.sayit.ui.setup_wizard import ModelSelectionPage

        page = ModelSelectionPage()
        qtbot.addWidget(page)
        page.set_language("hi")
        ids = {page._model_combo.itemData(i) for i in range(page._model_combo.count())}
        assert ids == {"indicconformer-hi-int8"}
        assert "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8" not in ids
