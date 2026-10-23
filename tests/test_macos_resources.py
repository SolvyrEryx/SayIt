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
    """Invoke package_macos_dmg with subprocess.run + the hdiutil DMG helper
    mocked; return the Briefcase argv.

    Briefcase 0.3.26 has NO ``--no-sign`` option for ``package macOS``; without
    an identity it must be invoked with ``--adhoc-sign`` (and ``--no-input`` so
    a headless CI runner never blocks on the interactive identity prompt). We
    package as ``--packaging-format zip`` so Briefcase SIGNS the .app without
    invoking dmgbuild (whose under-sized image caused the DMG failure); the DMG
    itself is then built by the payload-sized hdiutil helper.
    """
    build = _load_build_module()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _R:
            returncode = 0
            stdout = ""

        return _R()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    # Stub the native DMG helper (hdiutil is macOS-only; this test is about the
    # Briefcase signing invocation, verified cross-platform).
    dmg_calls = {}
    monkeypatch.setattr(
        build, "_make_dmg_hdiutil",
        lambda app_path, out_dmg, volume_name: dmg_calls.update(
            app=app_path, out=out_dmg, vol=volume_name
        ),
    )
    # package_macos_dmg now requires a signed .app to exist in the build tree.
    app = tmp_path / "build" / "sayit" / "macos" / "app" / "SayIt.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "SayIt").write_text("bin", encoding="utf-8")

    if env_identity is None:
        monkeypatch.delenv("SAYIT_MACOS_SIGN_IDENTITY", raising=False)
    else:
        monkeypatch.setenv("SAYIT_MACOS_SIGN_IDENTITY", env_identity)
    build.package_macos_dmg(tmp_path, "offline")
    captured["dmg"] = dmg_calls
    return captured["cmd"]


def test_macos_unsigned_uses_adhoc_sign_and_zip(monkeypatch, tmp_path):
    cmd = _capture_package_cmd(monkeypatch, tmp_path, env_identity=None)
    assert "package" in cmd and "macOS" in cmd
    assert "--adhoc-sign" in cmd, cmd
    assert "--no-input" in cmd, cmd
    # Signed .app only (no dmgbuild) -> packaging format zip.
    assert "--packaging-format" in cmd and "zip" in cmd, cmd
    # The invalid flag that caused the interactive-prompt abort must be gone.
    assert "--no-sign" not in cmd, cmd
    assert "--identity" not in cmd, cmd


def test_macos_signed_uses_identity(monkeypatch, tmp_path):
    cmd = _capture_package_cmd(
        monkeypatch, tmp_path, env_identity="Developer ID Application: Example"
    )
    assert "--identity" in cmd, cmd
    assert "Developer ID Application: Example" in cmd, cmd
    assert "--packaging-format" in cmd and "zip" in cmd, cmd
    assert "--adhoc-sign" not in cmd, cmd


# ---------------------------------------------------------------------------
# DMG capacity sizing (payload-sized image; platform-independent pure logic).
# ---------------------------------------------------------------------------
def test_dmg_capacity_small_online_bundle():
    build = _load_build_module()
    mib = 1024 * 1024
    # A small ~120 MiB online-style bundle: capacity must exceed payload and
    # include at least the 64 MiB minimum slack.
    payload = 120 * mib
    cap = build.compute_dmg_capacity_bytes(payload)
    assert cap > payload
    assert cap - payload >= 64 * mib  # minimum floor dominates for small bundles
    assert cap % mib == 0  # whole-MiB rounding


def test_dmg_capacity_large_offline_bundle_with_models():
    build = _load_build_module()
    mib = 1024 * 1024
    # ~1.6 GiB offline-style bundle (app + deps + 1.33 GiB models).
    payload = 1600 * mib
    cap = build.compute_dmg_capacity_bytes(payload)
    # For a large bundle the 30% headroom dominates the 64 MiB floor.
    assert cap >= payload + int(payload * 0.30)
    assert cap > payload


def test_dmg_capacity_crosses_headroom_boundary():
    build = _load_build_module()
    mib = 1024 * 1024
    # Just below where 30% overtakes the 64 MiB floor: 30% == 64 MiB at ~213 MiB.
    small = 100 * mib   # 30% = 30 MiB  -> floor (64 MiB) wins
    large = 400 * mib   # 30% = 120 MiB -> percentage wins
    cap_small = build.compute_dmg_capacity_bytes(small)
    cap_large = build.compute_dmg_capacity_bytes(large)
    assert cap_small - small == 64 * mib
    assert cap_large - large >= int(large * 0.30)


def test_dmg_capacity_rejects_invalid_payloads():
    import pytest

    build = _load_build_module()
    for bad in (0, -1, -1024, None, "100", 1.5):
        with pytest.raises(ValueError):
            build.compute_dmg_capacity_bytes(bad)  # type: ignore[arg-type]


def test_dmg_capacity_always_fits_payload():
    build = _load_build_module()
    mib = 1024 * 1024
    for payload in (1 * mib, 50 * mib, 213 * mib, 1333 * mib, 3000 * mib):
        cap = build.compute_dmg_capacity_bytes(payload)
        assert cap > payload, (payload, cap)
