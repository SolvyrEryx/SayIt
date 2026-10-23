"""Stage + verify the four INT8 ASR models for the Full Offline Installer.

Copies exactly the files listed in ``bundled_models.json`` from a source model
store into ``src/sayit/resources/bundled_models/<model_id>/`` and then verifies
every staged file against the version-controlled SHA-256 manifest. The script
FAILS (non-zero exit, raises) on any missing file, size mismatch, or hash
mismatch — a corrupted or swapped artifact can never be packaged silently.

Only the files named in the manifest are copied, so redundant FP32 Whisper
graphs are intentionally excluded (INT8-only offline bundle).

Usage:
  python scripts/stage_bundled_models.py \
      --source "<dir with one subdir per model id>" \
      [--dest src/sayit/resources/bundled_models] [--clean]

If --source is omitted, the per-user SayIt model cache is used.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.models.model_integrity import (  # noqa: E402
    ModelIntegrityError,
    load_bundled_manifest,
    verify_model_dir,
)


def default_source() -> str:
    return get_models_dir()


def stage(source: str, dest: str, clean: bool) -> int:
    manifest = load_bundled_manifest()
    dest_root = Path(dest)

    if clean and dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    for model in manifest:
        src_dir = Path(source) / model.id
        out_dir = dest_root / model.id
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"[stage] {model.id} ({model.role})")
        for spec in model.files:
            src_file = src_dir / spec.dest
            if not src_file.is_file():
                raise FileNotFoundError(
                    f"[{model.id}] source file not found: {src_file}"
                )
            out_file = out_dir / spec.dest
            out_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, out_file)
            total_bytes += out_file.stat().st_size
            print(f"         + {spec.dest} ({out_file.stat().st_size:,} bytes)")

        # Fail-fast integrity gate on the just-staged files.
        verify_model_dir(model, str(out_dir))
        print(f"         verified OK ({model.license})")

    print(
        f"\n[done] staged {len(manifest)} models, "
        f"{total_bytes / (1024 ** 3):.2f} GiB total, into {dest_root}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=None, help="Source model store directory")
    ap.add_argument(
        "--dest",
        default=str(REPO_ROOT / "src" / "sayit" / "resources" / "bundled_models"),
    )
    ap.add_argument("--clean", action="store_true", help="Remove dest first")
    args = ap.parse_args()

    source = args.source or default_source()
    if not os.path.isdir(source):
        print(f"ERROR: source directory not found: {source}", file=sys.stderr)
        return 2

    try:
        return stage(source, args.dest, args.clean)
    except (ModelIntegrityError, FileNotFoundError) as e:
        print(f"\nINTEGRITY GATE FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
