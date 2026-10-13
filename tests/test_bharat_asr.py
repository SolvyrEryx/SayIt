"""Tests for Hindi/Kannada ASR support: nemo_ctc loader routing, registry
language metadata, and language-aware model routing.

These are fast tests: no model weights are downloaded and sherpa-onnx is not
invoked. The actual from_nemo_ctc call is mocked so we verify routing/wiring
without the ~190 MB IndicConformer weights.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.sayit.core.asr import file_utils
from src.sayit.core.asr import language_routing as lr
from src.sayit.core.asr.backends import SherpaOnnxBackend, get_model_type
from src.sayit.core.asr.models.registry import (
    get_available_languages,
    get_model_by_id,
    get_models_for_language,
)


class TestRegistryLanguageMetadata:
    def test_hindi_kannada_models_registered(self):
        hi = get_models_for_language("hi")
        kn = get_models_for_language("kn")
        assert any(m.id == "indicconformer-hi-int8" for m in hi)
        assert any(m.id == "indicconformer-kn-int8" for m in kn)

    def test_indic_models_are_nemo_ctc_and_multifile(self):
        for mid in ("indicconformer-hi-int8", "indicconformer-kn-int8"):
            m = get_model_by_id(mid)
            assert m is not None
            assert m.type == "nemo_ctc"
            assert m.is_multi_file
            dests = {f.dest for f in m.files}
            assert "model.int8.onnx" in dests
            assert "tokens.txt" in dests
            assert m.license  # provenance/license recorded

    def test_english_models_still_present_and_tagged_en(self):
        en = get_models_for_language("en")
        assert any(m.id == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8" for m in en)
        for m in en:
            assert m.language == "en"

    def test_available_languages_english_first(self):
        langs = get_available_languages()
        assert langs[0] == "en"
        assert "hi" in langs and "kn" in langs

    def test_get_model_type_nemo_ctc(self):
        assert get_model_type("indicconformer-hi-int8") == "nemo_ctc"


class TestNemoCtcLoaderRouting:
    def test_load_routes_nemo_ctc_to_from_nemo_ctc(self, tmp_path):
        # Create a fake model dir that looks like a valid nemo_ctc model.
        model_dir = tmp_path / "indicconformer-hi-int8"
        model_dir.mkdir()
        (model_dir / "model.int8.onnx").write_bytes(b"\x00")
        (model_dir / "tokens.txt").write_text("a 1\n")

        fake_sherpa = MagicMock()
        backend = SherpaOnnxBackend()
        with patch.dict("sys.modules", {"sherpa_onnx": fake_sherpa}):
            with patch(
                "src.sayit.core.asr.backends.get_model_type", return_value="nemo_ctc"
            ):
                backend.load(str(model_dir))
        # The nemo_ctc factory must have been used, not whisper/transducer.
        assert fake_sherpa.OfflineRecognizer.from_nemo_ctc.called
        assert not fake_sherpa.OfflineRecognizer.from_whisper.called
        assert not fake_sherpa.OfflineRecognizer.from_transducer.called

    def test_nemo_ctc_missing_files_raises(self, tmp_path):
        model_dir = tmp_path / "broken"
        model_dir.mkdir()
        # Only tokens, no model.onnx
        (model_dir / "tokens.txt").write_text("a 1\n")
        fake_sherpa = MagicMock()
        backend = SherpaOnnxBackend()
        with patch.dict("sys.modules", {"sherpa_onnx": fake_sherpa}):
            with patch(
                "src.sayit.core.asr.backends.get_model_type", return_value="nemo_ctc"
            ):
                with pytest.raises(RuntimeError):
                    backend.load(str(model_dir))


class TestNemoCtcValidation:
    def test_is_valid_nemo_ctc_model(self, tmp_path):
        d = tmp_path / "m"
        d.mkdir()
        assert file_utils.is_valid_nemo_ctc_model(str(d)) is False
        (d / "model.int8.onnx").write_bytes(b"\x00")
        (d / "tokens.txt").write_text("a 1\n")
        assert file_utils.is_valid_nemo_ctc_model(str(d)) is True

    def test_is_valid_model_dir_accepts_nemo_ctc(self, tmp_path):
        d = tmp_path / "m"
        d.mkdir()
        (d / "model.int8.onnx").write_bytes(b"\x00")
        (d / "tokens.txt").write_text("a 1\n")
        assert file_utils.is_valid_model_dir(str(d)) is True


class TestLanguageRouting:
    def test_hi_never_routes_to_english(self):
        r = lr.resolve_model_for_language(
            "hi", current_model_id="sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        )
        assert r.model_id == "indicconformer-hi-int8"
        assert r.compatible

    def test_kn_resolves_to_kannada_model(self):
        r = lr.resolve_model_for_language("kn")
        assert r.model_id == "indicconformer-kn-int8"

    def test_is_compatible_rejects_crosslanguage(self):
        assert not lr.is_compatible("hi", "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8")
        assert lr.is_compatible("hi", "indicconformer-hi-int8")

    def test_check_pairing_explains_mismatch(self):
        res = lr.check_language_model_pairing(
            "kn", "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        )
        assert res.compatible is False
        assert "kn" in res.reason

    def test_unknown_language_reports_no_model(self):
        res = lr.resolve_model_for_language("zz")
        assert res.model_id is None
        assert res.compatible is False
