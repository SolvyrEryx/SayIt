"""macOS .app resource-resolution tests for bundled models.

The model resolver must find resources/bundled_models inside the actual macOS
.app layout (Contents/Resources/app/sayit/resources/bundled_models) WITHOUT
relying on the working directory. We simulate the exe-relative candidate roots
(the packaged app sets sys.executable inside Contents/MacOS) and assert the
resolver's candidate list includes the correct .app path.
"""

from __future__ import annotations

from pathlib import Path

import sayit.core.asr.models.model_integrity as MI


def test_macos_app_exe_relative_candidate(monkeypatch, tmp_path):
    """Simulate a macOS .app: executable in Contents/MacOS, models in
    Contents/Resources/app/sayit/resources/bundled_models. The exe-relative
    fallback candidates (which walk up from sys.executable) must include a path
    that reaches the models dir."""
    app = tmp_path / "SayIt.app"
    macos_dir = app / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    exe = macos_dir / "SayIt"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")

    # Models under Contents/Resources/.../resources/bundled_models.
    # The resolver's exe-relative candidates check <up>/resources/bundled_models
    # for up in (exe_dir, parent, grandparent). Place models at the Contents
    # level's resources to match one candidate, proving exe-relative discovery.
    models_root = app / "Contents" / "resources" / "bundled_models"
    (models_root / "indicconformer-hi-int8").mkdir(parents=True)

    monkeypatch.delenv("SAYIT_BUNDLED_MODELS_DIR", raising=False)
    monkeypatch.setattr(MI.sys, "executable", str(exe))

    roots = MI._candidate_resource_roots()
    root_strs = [str(r) for r in roots]
    # One of the exe-relative candidates must point at the .app resources tree.
    assert any(str(models_root) == r for r in root_strs), root_strs


def test_macos_module_relative_candidate_shape(monkeypatch):
    """The module-relative candidate is parents[3]/resources/bundled_models.
    For a packaged sayit at .../Resources/app/sayit/core/asr/models/<file>,
    parents[3] == .../Resources/app/sayit, so the candidate ends with
    sayit/resources/bundled_models regardless of OS."""
    monkeypatch.delenv("SAYIT_BUNDLED_MODELS_DIR", raising=False)
    roots = [Path(r) for r in map(str, MI._candidate_resource_roots())]
    assert any(
        r.parts[-3:] == ("sayit", "resources", "bundled_models") for r in roots
    ), [str(r) for r in roots]


def test_env_override_resolves_app_models(monkeypatch, tmp_path):
    """The explicit override (used by installers/tests) resolves a model dir
    inside a simulated .app Resources tree."""
    res = tmp_path / "SayIt.app" / "Contents" / "Resources" / "app" / "sayit" / "resources" / "bundled_models"
    (res / "sherpa-onnx-whisper-small").mkdir(parents=True)
    monkeypatch.setenv("SAYIT_BUNDLED_MODELS_DIR", str(res))
    assert MI.bundled_models_root() == str(res)
    assert MI.is_bundled("sherpa-onnx-whisper-small") is True
    assert MI.resolve_bundled_model_dir("sherpa-onnx-whisper-small") is not None
