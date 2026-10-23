"""Regression tests for bundle-aware model availability (v0.2.0).

Ensures a bundled offline-installer model is treated as available (no download),
that cache presence takes precedence over bundled, and that language routing +
speech-mode status reflect bundled availability without crossing languages.
"""

from __future__ import annotations

import sayit.core.asr.models.registry as reg
from sayit.core.asr import speech_mode as SM
from sayit.core.asr.models import model_integrity as MI


def _patch_empty_cache(tmp_path, monkeypatch):
    """Point the user model cache at an empty dir so only bundled matters."""
    empty = tmp_path / "cache"
    empty.mkdir()
    monkeypatch.setattr(reg, "get_models_dir", lambda: str(empty))
    return empty


def _patch_bundled(monkeypatch, bundled_ids):
    monkeypatch.setattr(reg, "is_bundled", lambda mid: mid in bundled_ids)

    def _resolve(mid):
        return f"/bundled/{mid}" if mid in bundled_ids else None

    monkeypatch.setattr(reg, "resolve_bundled_model_dir", _resolve)


def test_bundled_model_is_available_without_download(tmp_path, monkeypatch):
    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {"indicconformer-hi-int8"})
    assert reg.is_model_downloaded("indicconformer-hi-int8") is True
    assert reg.get_model_download_status("indicconformer-hi-int8") == "bundled"
    assert reg.is_model_available("indicconformer-hi-int8") is True


def test_not_present_model_is_not_downloaded(tmp_path, monkeypatch):
    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, set())
    assert reg.is_model_downloaded("sherpa-onnx-whisper-small") is False
    assert (
        reg.get_model_download_status("sherpa-onnx-whisper-small") == "not_downloaded"
    )


def test_cache_takes_precedence_over_bundled(tmp_path, monkeypatch):
    cache = _patch_empty_cache(tmp_path, monkeypatch)
    # Create a valid cached nemo_ctc model dir.
    mid = "indicconformer-hi-int8"
    d = cache / mid
    d.mkdir()
    (d / "model.int8.onnx").write_bytes(b"x")
    (d / "tokens.txt").write_bytes(b"t")
    _patch_bundled(monkeypatch, {mid})
    assert reg.get_model_download_status(mid) == "downloaded"
    # resolve_model_location prefers the cache copy
    loc = reg.resolve_model_location(mid)
    assert loc is not None and str(cache) in loc


def test_resolve_model_location_falls_back_to_bundled(tmp_path, monkeypatch):
    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {"indicconformer-kn-int8"})
    loc = reg.resolve_model_location("indicconformer-kn-int8")
    assert loc == "/bundled/indicconformer-kn-int8"


def test_installed_list_includes_bundled(tmp_path, monkeypatch):
    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {"indicconformer-hi-int8", "indicconformer-kn-int8"})
    installed = reg.get_installed_asr_models()
    assert "indicconformer-hi-int8" in installed
    assert "indicconformer-kn-int8" in installed


def test_speech_mode_bundled_status(tmp_path, monkeypatch):
    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {SM.FAST_MODEL_ID, SM.HIGHER_ACCURACY_MODEL_ID})
    assert "Bundled" in SM.mode_status(SM.FAST)
    assert "Bundled" in SM.mode_status(SM.HIGHER_ACCURACY)
    assert SM.is_mode_available(SM.HIGHER_ACCURACY) is True


def test_language_routing_prefers_bundled_indic(tmp_path, monkeypatch):
    from sayit.core.asr import language_routing as LR

    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {"indicconformer-hi-int8", "indicconformer-kn-int8"})
    for lang, expected in (
        ("hi", "indicconformer-hi-int8"),
        ("kn", "indicconformer-kn-int8"),
    ):
        r = LR.resolve_model_for_language(lang)
        assert r.model_id == expected
        assert r.installed is True
        assert r.compatible is True


def test_language_routing_never_crosses_to_english(tmp_path, monkeypatch):
    """A Hindi request must never resolve to an English-only model."""
    from sayit.core.asr import language_routing as LR

    _patch_empty_cache(tmp_path, monkeypatch)
    _patch_bundled(monkeypatch, {SM.FAST_MODEL_ID})  # only English bundled
    r = LR.resolve_model_for_language("hi")
    assert r.model_id != SM.FAST_MODEL_ID
    assert r.model_id == "indicconformer-hi-int8"  # canonical hi default
    assert r.compatible is True
