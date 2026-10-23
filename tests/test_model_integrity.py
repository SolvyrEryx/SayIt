"""Regression tests for bundled-model integrity + availability (v0.2.0).

Covers the version-controlled manifest, the build-time integrity gate (passes
on good files, FAILS on tamper / missing file), bundled resolution, and the
registry/speech_mode/language-routing bundle-awareness. No real model weights
are needed: tiny fixture files are created and the manifest is monkeypatched to
reference them, so the gate logic is exercised deterministically.
"""

from __future__ import annotations

import hashlib

import pytest

from sayit.core.asr.models import model_integrity as MI


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_model(tmp_path, model_id="m1", content=b"weights"):
    d = tmp_path / model_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.int8.onnx").write_bytes(content)
    (d / "tokens.txt").write_bytes(b"tok")
    return d


def _fixture_manifest(model_id, model_content=b"weights"):
    return [
        MI.BundledModel(
            id=model_id,
            role="test",
            name="Test",
            type="nemo_ctc",
            language="hi",
            source="test",
            license="MIT",
            attribution="test",
            files=[
                MI.BundledFile(
                    "model.int8.onnx", len(model_content), _sha(model_content)
                ),
                MI.BundledFile("tokens.txt", 3, _sha(b"tok")),
            ],
        )
    ]


def test_real_manifest_loads_four_models():
    models = MI.load_bundled_manifest()
    ids = {m.id for m in models}
    assert ids == {
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
        "sherpa-onnx-whisper-small",
        "indicconformer-hi-int8",
        "indicconformer-kn-int8",
    }
    roles = {m.role for m in models}
    assert roles == {"english_fast", "english_higher_accuracy", "hindi", "kannada"}
    # Every file has a non-empty 64-hex sha256.
    for m in models:
        assert m.files
        for f in m.files:
            assert len(f.sha256) == 64
            int(f.sha256, 16)  # valid hex


def test_indic_manifest_hashes_match_models_json():
    """The bundled Indic hashes must equal the per-file sha256 already in
    models.json (the download-on-demand source of truth)."""
    import json
    from pathlib import Path

    models_json = json.loads(
        (Path(MI.__file__).parent / "models.json").read_text(encoding="utf-8")
    )
    by_id = {m["id"]: m for m in models_json}
    for mid in ("indicconformer-hi-int8", "indicconformer-kn-int8"):
        manifest_model = next(m for m in MI.load_bundled_manifest() if m.id == mid)
        json_files = {f["dest"]: f["sha256"].lower() for f in by_id[mid]["files"]}
        for f in manifest_model.files:
            assert f.sha256 == json_files[f.dest], f"{mid}/{f.dest} hash drift"


def test_gate_passes_on_good_files(tmp_path, monkeypatch):
    _make_model(tmp_path, "m1")
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: _fixture_manifest("m1"))
    verified = MI.verify_staged_models(str(tmp_path))
    assert "m1" in verified


def test_gate_fails_on_hash_tamper(tmp_path, monkeypatch):
    d = _make_model(tmp_path, "m1")
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: _fixture_manifest("m1"))
    # Tamper the content so the hash no longer matches (same length).
    (d / "model.int8.onnx").write_bytes(b"XXXXXXX")
    with pytest.raises(MI.ModelIntegrityError):
        MI.verify_staged_models(str(tmp_path))


def test_gate_fails_on_size_mismatch(tmp_path, monkeypatch):
    d = _make_model(tmp_path, "m1")
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: _fixture_manifest("m1"))
    (d / "model.int8.onnx").write_bytes(b"weights-extra")  # wrong size
    with pytest.raises(MI.ModelIntegrityError):
        MI.verify_staged_models(str(tmp_path))


def test_gate_fails_on_missing_file(tmp_path, monkeypatch):
    d = _make_model(tmp_path, "m1")
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: _fixture_manifest("m1"))
    (d / "tokens.txt").unlink()
    with pytest.raises(MI.ModelIntegrityError):
        MI.verify_staged_models(str(tmp_path))


def test_gate_fails_on_missing_model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: _fixture_manifest("m1"))
    with pytest.raises(MI.ModelIntegrityError):
        MI.verify_staged_models(str(tmp_path))


def test_resolution_via_env_override(tmp_path, monkeypatch):
    _make_model(tmp_path, "indicconformer-hi-int8")
    monkeypatch.setenv("SAYIT_BUNDLED_MODELS_DIR", str(tmp_path))
    assert MI.bundled_models_root() == str(tmp_path)
    assert MI.is_bundled("indicconformer-hi-int8") is True
    assert MI.resolve_bundled_model_dir("indicconformer-hi-int8") is not None
    assert MI.is_bundled("nope") is False


def test_no_resources_means_not_bundled(monkeypatch):
    monkeypatch.delenv("SAYIT_BUNDLED_MODELS_DIR", raising=False)
    monkeypatch.setattr(MI, "_candidate_resource_roots", lambda: [])
    assert MI.bundled_models_root() is None
    assert MI.is_bundled("indicconformer-hi-int8") is False
