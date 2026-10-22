"""Build-isolation regression tests for scripts/build.py (v0.2.0).

These verify the deterministic, order-independent isolation between the two
Windows installer variants WITHOUT performing real multi-GB Briefcase builds:

* ``clean_staging`` removes the source-tree bundled-model staging dir.
* ``gate_offline_contents`` passes only when the packaged app tree contains
  exactly the four approved models (fails on missing / unexpected / tampered).
* ``gate_ondemand_contents`` fails if ANY bundled model weight leaks into the
  smaller app tree, and passes when the tree is model-free.

Both build orders (offline->ondemand and ondemand->offline) are simulated by
constructing the corresponding packaged trees and asserting the gate verdicts,
which is what actually guards the real build.

The real Briefcase/ISCC build is exercised separately and manually (it needs
~1.3 GiB of weights + Inno Setup); here we test the guard logic with fixtures.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

build = importlib.import_module("build")
from sayit.core.asr.models import model_integrity as MI  # noqa: E402


# --- fixtures ---------------------------------------------------------------
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture_manifest():
    """Two tiny fake models standing in for the real four."""
    out = []
    for mid, lang in (("model-a-int8", "en"), ("model-b-int8", "hi")):
        content = f"weights-{mid}".encode()
        out.append(
            MI.BundledModel(
                id=mid,
                role="test",
                name=mid,
                type="nemo_ctc",
                language=lang,
                source="test",
                license="MIT",
                attribution="test",
                files=[
                    MI.BundledFile("model.int8.onnx", len(content), _sha(content)),
                    MI.BundledFile("tokens.txt", 3, _sha(b"tok")),
                ],
            )
        )
    return out


def _write_model(models_dir: Path, model, *, tamper=False):
    d = models_dir / model.id
    d.mkdir(parents=True, exist_ok=True)
    for f in model.files:
        if f.dest == "model.int8.onnx":
            data = b"XXXXXXX" if tamper else f"weights-{model.id}".encode()
        else:
            data = b"tok"
        (d / f.dest).write_bytes(data)


def _make_windows_app_tree(tmp_path: Path) -> Path:
    """Create build/sayit/windows/app/src/app/sayit/resources/... skeleton.

    Returns the project_root to pass to the gate functions.
    """
    root = tmp_path / "proj"
    app_src = root / "build" / "sayit" / "windows" / "app" / "src"
    (app_src / "app" / "sayit" / "resources").mkdir(parents=True, exist_ok=True)
    # a couple of non-model package files so the tree is not empty
    (app_src / "app" / "sayit" / "__init__.py").write_text("x", encoding="utf-8")
    return root


def _offline_models_dir(root: Path) -> Path:
    return build.packaged_app_models_dir(root, "windows")


@pytest.fixture
def patched_manifest(monkeypatch):
    fm = _fixture_manifest()
    monkeypatch.setattr(MI, "load_bundled_manifest", lambda: fm)
    # build.py imports these names lazily from MI inside the gate, so patching
    # MI is sufficient.
    return fm


# --- clean_staging ----------------------------------------------------------
def test_clean_staging_removes_dir(tmp_path):
    root = tmp_path / "proj"
    staging = root / build.STAGING_REL
    staging.mkdir(parents=True)
    (staging / "model-a-int8").mkdir()
    (staging / "model-a-int8" / "model.int8.onnx").write_bytes(b"x")
    assert staging.exists()
    build.clean_staging(root)
    assert not staging.exists()


def test_clean_staging_noop_when_absent(tmp_path):
    root = tmp_path / "proj"
    # must not raise when there is nothing to clean
    build.clean_staging(root)
    assert not (root / build.STAGING_REL).exists()


# --- offline gate -----------------------------------------------------------
def test_offline_gate_passes_with_all_models(tmp_path, patched_manifest):
    root = _make_windows_app_tree(tmp_path)
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    for m in patched_manifest:
        _write_model(md, m)
    build.gate_offline_contents(root, "windows")  # must not raise


def test_offline_gate_fails_on_missing_model(tmp_path, patched_manifest):
    root = _make_windows_app_tree(tmp_path)
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    _write_model(md, patched_manifest[0])  # only one of two
    with pytest.raises(build.BuildIsolationError, match="missing required model"):
        build.gate_offline_contents(root, "windows")


def test_offline_gate_fails_on_unexpected_model(tmp_path, patched_manifest):
    root = _make_windows_app_tree(tmp_path)
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    for m in patched_manifest:
        _write_model(md, m)
    (md / "rogue-model").mkdir()
    (md / "rogue-model" / "model.int8.onnx").write_bytes(b"nope")
    with pytest.raises(build.BuildIsolationError, match="unexpected model id"):
        build.gate_offline_contents(root, "windows")


def test_offline_gate_fails_on_tampered_weights(tmp_path, patched_manifest):
    root = _make_windows_app_tree(tmp_path)
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    _write_model(md, patched_manifest[0])
    _write_model(md, patched_manifest[1], tamper=True)  # wrong hash
    with pytest.raises(MI.ModelIntegrityError):
        build.gate_offline_contents(root, "windows")


def test_offline_gate_fails_when_dir_absent(tmp_path, patched_manifest):
    root = _make_windows_app_tree(tmp_path)
    with pytest.raises(build.BuildIsolationError, match="bundled_models dir missing"):
        build.gate_offline_contents(root, "windows")


# --- ondemand gate ----------------------------------------------------------
def test_ondemand_gate_passes_when_model_free(tmp_path):
    root = _make_windows_app_tree(tmp_path)
    build.gate_ondemand_contents(root, "windows")  # must not raise


def test_ondemand_gate_fails_when_bundled_dir_present(tmp_path):
    root = _make_windows_app_tree(tmp_path)
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    (md / "model-a-int8").mkdir()
    (md / "model-a-int8" / "model.int8.onnx").write_bytes(b"leak")
    with pytest.raises(build.BuildIsolationError, match="must NOT exist"):
        build.gate_ondemand_contents(root, "windows")


def test_ondemand_gate_fails_on_leaked_onnx_in_resources(tmp_path):
    root = _make_windows_app_tree(tmp_path)
    # a stray .onnx under resources (not a bundled_models dir) must still fail
    res = (
        root / "build" / "sayit" / "windows" / "app" / "src" / "app" / "sayit"
        / "resources"
    )
    (res / "stray.onnx").write_bytes(b"leak")
    with pytest.raises(build.BuildIsolationError, match="leaked"):
        build.gate_ondemand_contents(root, "windows")


# --- build-order independence (simulated) -----------------------------------
def test_order_offline_then_ondemand(tmp_path, patched_manifest):
    """After an offline build, an ondemand build cleans staging and must pass
    the ondemand gate (no models), while a fresh offline tree passes offline."""
    root = _make_windows_app_tree(tmp_path)

    # 1) offline: models present -> offline gate passes
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    for m in patched_manifest:
        _write_model(md, m)
    build.gate_offline_contents(root, "windows")

    # 2) switch to ondemand: build.py removes the staging + recreates the tree.
    #    Simulate by clearing the models dir, then the ondemand gate must pass.
    import shutil

    shutil.rmtree(md)
    build.gate_ondemand_contents(root, "windows")


def test_order_ondemand_then_offline(tmp_path, patched_manifest):
    """After an ondemand build, an offline build stages all models and must
    pass the offline gate."""
    root = _make_windows_app_tree(tmp_path)

    # 1) ondemand: no models -> ondemand gate passes
    build.gate_ondemand_contents(root, "windows")

    # 2) switch to offline: stage all models -> offline gate passes
    md = _offline_models_dir(root)
    md.mkdir(parents=True)
    for m in patched_manifest:
        _write_model(md, m)
    build.gate_offline_contents(root, "windows")
