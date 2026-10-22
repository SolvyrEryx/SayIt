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


# ---------------------------------------------------------------------------
# macOS DMG packaging command construction (regression for CI exit-214 abort).
# ---------------------------------------------------------------------------
def _load_build_module():
    import importlib
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("build")


def _capture_package_cmd(monkeypatch, tmp_path, env_identity):
    """Invoke package_macos_dmg with subprocess.run mocked; return the argv.

    Briefcase 0.3.26 has NO ``--no-sign`` option for ``package macOS``; without
    an identity it must be invoked with ``--adhoc-sign`` (and ``--no-input`` so
    a headless CI runner never blocks on the interactive identity prompt, which
    previously aborted the job with exit code 214).
    """
    build = _load_build_module()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    if env_identity is None:
        monkeypatch.delenv("SAYIT_MACOS_SIGN_IDENTITY", raising=False)
    else:
        monkeypatch.setenv("SAYIT_MACOS_SIGN_IDENTITY", env_identity)
    # No dist/*.dmg present -> the function returns after the mocked run.
    build.package_macos_dmg(tmp_path, "offline")
    return captured["cmd"]


def test_macos_unsigned_uses_adhoc_sign_and_no_input(monkeypatch, tmp_path):
    cmd = _capture_package_cmd(monkeypatch, tmp_path, env_identity=None)
    assert "package" in cmd and "macOS" in cmd
    assert "--adhoc-sign" in cmd, cmd
    assert "--no-input" in cmd, cmd
    # The invalid flag that caused the interactive-prompt abort must be gone.
    assert "--no-sign" not in cmd, cmd
    assert "--identity" not in cmd, cmd


def test_macos_signed_uses_identity(monkeypatch, tmp_path):
    cmd = _capture_package_cmd(monkeypatch, tmp_path, env_identity="Developer ID Application: Example")
    assert "--identity" in cmd, cmd
    assert "Developer ID Application: Example" in cmd, cmd
    assert "--adhoc-sign" not in cmd, cmd
