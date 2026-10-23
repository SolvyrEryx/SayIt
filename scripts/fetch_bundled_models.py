"""Fetch + verify the bundled offline-installer models into the model cache.

Downloads exactly the model ids listed in the committed bundled-model manifest
(``bundled_models.json``) using the existing integrity-checked downloader, which
verifies every file against the per-file SHA-256 in ``models.json``. Intended
for CI, where no pre-populated user model cache exists.

This does NOT stage into the app; it only populates the cache so that
``scripts/stage_bundled_models.py`` can copy + re-verify from it. It never
regenerates or rewrites any hash.

Usage:
  python scripts/fetch_bundled_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.models.downloader import ModelDownloader  # noqa: E402
from sayit.core.asr.models.model_integrity import (  # noqa: E402
    load_bundled_manifest,
    verify_model_dir,
)
from sayit.core.asr.models.registry import is_model_downloaded  # noqa: E402


def main() -> int:
    manifest = load_bundled_manifest()
    cache = get_models_dir()
    downloader = ModelDownloader()

    print(f"Fetching {len(manifest)} bundled models into cache: {cache}")
    for model in manifest:
        print(f"\n[fetch] {model.id} ({model.role}, {model.license})")
        if is_model_downloaded(model.id):
            print("  already present in cache")
        else:
            ok = downloader.download(
                model.id,
                on_status=lambda s: print(f"  {s}"),
            )
            if not ok:
                print(f"ERROR: download failed for {model.id}", file=sys.stderr)
                return 1

        # Fail-fast integrity verification of the cached copy against the
        # committed manifest (never regenerate a hash).
        model_dir = str(Path(cache) / model.id)
        verify_model_dir(model, model_dir)
        print("  verified OK against bundled_models.json")

    print(f"\n[done] all {len(manifest)} bundled models fetched + verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
