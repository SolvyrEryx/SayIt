"""Bundled-model integrity, provenance, and resolution.

The SayIt Full Offline Installer ships four validated INT8 ASR models inside
the application's installation resources. This module:

* Loads the version-controlled manifest ``bundled_models.json`` (SHA-256 of
  every bundled file plus provenance/license).
* Verifies staged model files against those hashes and **fails on any mismatch
  or missing file** (used by the build staging step so a corrupted or swapped
  artifact can never be packaged silently).
* Resolves bundled models directly from the install resources so the app can
  load them **without copying them into the per-user model cache** (no
  duplication on disk).

Nothing here fabricates hashes: verification only ever *compares* a freshly
computed digest to the reviewed expected value in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_MANIFEST_NAME = "bundled_models.json"


class ModelIntegrityError(Exception):
    """Raised when a bundled model file is missing or fails hash verification."""


@dataclass(frozen=True)
class BundledFile:
    dest: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BundledModel:
    id: str
    role: str
    name: str
    type: str
    language: str
    source: str
    license: str
    attribution: str
    files: List[BundledFile] = field(default_factory=list)
    note: str = ""


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent / _MANIFEST_NAME


def load_bundled_manifest() -> List[BundledModel]:
    """Load and parse the version-controlled bundled-model manifest."""
    path = _manifest_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    models: List[BundledModel] = []
    for item in data.get("models", []):
        files = [
            BundledFile(dest=f["dest"], size=int(f["size"]), sha256=f["sha256"].lower())
            for f in item.get("files", [])
        ]
        models.append(
            BundledModel(
                id=item["id"],
                role=item["role"],
                name=item["name"],
                type=item["type"],
                language=item["language"],
                source=item["source"],
                license=item["license"],
                attribution=item["attribution"],
                files=files,
                note=item.get("note", ""),
            )
        )
    return models


def bundled_model_ids() -> List[str]:
    return [m.id for m in load_bundled_manifest()]


def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    """Stream a SHA-256 of ``path`` without loading it fully into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_model_dir(model: BundledModel, model_dir: str) -> None:
    """Verify every file of ``model`` under ``model_dir``.

    Raises ``ModelIntegrityError`` on a missing file, wrong size, or SHA-256
    mismatch. Never mutates files.
    """
    for spec in model.files:
        fp = os.path.join(model_dir, spec.dest)
        if not os.path.isfile(fp):
            raise ModelIntegrityError(f"[{model.id}] missing bundled file: {spec.dest}")
        actual_size = os.path.getsize(fp)
        if spec.size and actual_size != spec.size:
            raise ModelIntegrityError(
                f"[{model.id}] size mismatch for {spec.dest}: "
                f"expected {spec.size}, got {actual_size}"
            )
        actual_hash = sha256_file(fp)
        if actual_hash != spec.sha256:
            raise ModelIntegrityError(
                f"[{model.id}] SHA-256 mismatch for {spec.dest}: "
                f"expected {spec.sha256}, got {actual_hash}"
            )


def verify_staged_models(staging_root: str) -> Dict[str, str]:
    """Build-time gate: verify every manifest model staged under ``staging_root``.

    ``staging_root`` is expected to contain one sub-directory per model id.
    Returns a map ``{model_id: absolute_model_dir}`` on full success. Raises
    ``ModelIntegrityError`` on the first problem so the build fails fast.
    """
    verified: Dict[str, str] = {}
    for model in load_bundled_manifest():
        model_dir = os.path.join(staging_root, model.id)
        if not os.path.isdir(model_dir):
            raise ModelIntegrityError(
                f"[{model.id}] staged model directory not found: {model_dir}"
            )
        verify_model_dir(model, model_dir)
        verified[model.id] = os.path.abspath(model_dir)
    return verified


# ---------------------------------------------------------------------------
# Runtime resolution of bundled models (no copy into the user model cache)
# ---------------------------------------------------------------------------
def _candidate_resource_roots() -> List[Path]:
    """Directories that may contain the packaged ``bundled_models`` tree.

    Covers the Briefcase/packaged layout, a PyInstaller-style ``sys._MEIPASS``
    frozen layout, and a dev/source checkout. Order is most-specific first.
    """
    roots: List[Path] = []

    # 1) Explicit override (used by tests / custom installs).
    override = os.environ.get("SAYIT_BUNDLED_MODELS_DIR")
    if override:
        roots.append(Path(override))

    # 2) Next to this package: src/sayit/resources/bundled_models (dev) or the
    #    packaged equivalent under the app's app_packages/sayit tree.
    pkg_root = Path(__file__).resolve().parents[3]  # .../sayit
    roots.append(pkg_root / "resources" / "bundled_models")

    # 3) Frozen bundle (PyInstaller) temp extraction dir.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "sayit" / "resources" / "bundled_models")

    # 4) Briefcase Windows layout: <app>/src/app_packages/sayit/resources/...
    #    Walk up from the executable directory as a fallback.
    try:
        exe_dir = Path(sys.executable).resolve().parent
        for up in (exe_dir, exe_dir.parent, exe_dir.parent.parent):
            roots.append(up / "resources" / "bundled_models")
            roots.append(up / "app_packages" / "sayit" / "resources" / "bundled_models")
    except Exception:
        pass

    return roots


def bundled_models_root() -> Optional[str]:
    """Return the first existing bundled-models root, or None if not packaged."""
    for root in _candidate_resource_roots():
        if root.is_dir():
            return str(root)
    return None


def resolve_bundled_model_dir(model_id: str) -> Optional[str]:
    """Absolute path to a bundled model's directory inside install resources.

    Returns None when the model is not part of the offline bundle or the
    bundled resources are not present (download-on-demand install).
    """
    root = bundled_models_root()
    if not root:
        return None
    model_dir = os.path.join(root, model_id)
    return model_dir if os.path.isdir(model_dir) else None


def is_bundled(model_id: str) -> bool:
    return resolve_bundled_model_dir(model_id) is not None
