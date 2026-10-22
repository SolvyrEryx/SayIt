"""SayIt Briefcase build driver.

Supports two Windows installer variants:

  --variant ondemand  (default)  Smaller installer. Model weights are downloaded
                                  on first use into the per-user model cache. The
                                  bundled-model staging directory is REMOVED and
                                  a validation gate fails the build if any bundled
                                  model weight leaks into the packaged app tree.
  --variant offline               Full Offline Installer. The four validated
                                  INT8 models are staged into the app under
                                  resources/bundled_models and verified against
                                  the committed SHA-256 manifest BEFORE being
                                  packaged. A hash/size mismatch, a missing model,
                                  or an unexpected model fails the build.

Build isolation (deterministic, order-independent):

* The bundled-model staging directory (src/sayit/resources/bundled_models) is
  always cleaned at the start of a build and tailored to the requested variant:
  populated+verified for ``offline``, removed for ``ondemand``.
* The per-variant Briefcase build tree is recreated from scratch
  (``briefcase create --no-input`` after removing the previous app tree), so the
  result never depends on which variant was built previously.
* A pre-package validation gate inspects the actual packaged app tree:
  - offline  -> MUST contain exactly the four approved model sets (fails if any
    required model/file is missing or if an unexpected model id appears);
  - ondemand -> MUST contain NO bundled model weights at all (fails otherwise).

Nothing here touches the per-user model cache or the version-controlled model
manifests; hashes are only ever compared, never regenerated.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Canonical source-tree staging location for bundled offline models. Briefcase
# copies the whole ``src/sayit`` package, so whatever is here at build time ends
# up inside the packaged app. This is the single place the variant isolation
# logic adds to (offline) or removes from (ondemand).
STAGING_REL = Path("src") / "sayit" / "resources" / "bundled_models"


def inject_version(project_root: Path, version: str) -> None:
    print(f"Injecting version: {version}")
    for rel, pattern, repl in (
        ("pyproject.toml", r'^version = "[^"]+"', f'version = "{version}"'),
        (
            "src/sayit/__init__.py",
            r'^__version__ = "[^"]+"',
            f'__version__ = "{version}"',
        ),
    ):
        p = project_root / rel
        p.write_text(
            re.sub(
                pattern, repl, p.read_text(encoding="utf-8"), flags=re.MULTILINE
            ),
            encoding="utf-8",
        )
        print(f"  Updated {p}")


def get_platform_target() -> tuple[str, str]:
    system = platform.system().lower()
    if system == "linux":
        return ("linux", "appimage")
    if system == "windows":
        return ("windows", "app")
    if system == "darwin":
        return ("macOS", "app")
    raise RuntimeError(f"Unsupported platform: {system}")


def generate_icons(project_root: Path) -> None:
    generator = project_root / "scripts" / "generate_icons.py"
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    print("\nGenerating SayIt application icons...")
    subprocess.run(
        [sys.executable, str(generator)], cwd=project_root, env=env, check=True
    )


# ---------------------------------------------------------------------------
# Build isolation
# ---------------------------------------------------------------------------
def clean_staging(project_root: Path) -> None:
    """Remove the source-tree bundled-model staging dir (if any).

    Only ever removes the one explicit staging path inside the repo. Never
    touches the per-user model cache.
    """
    staging = project_root / STAGING_REL
    if staging.exists():
        shutil.rmtree(staging)
        print(f"[isolation] removed stale staging dir: {staging}")


def clean_build_tree(project_root: Path, plat: str, fmt: str) -> None:
    """Remove the previous per-variant Briefcase app tree so ``create`` starts
    clean and the output never inherits a prior variant's staged resources."""
    app_tree = project_root / "build" / "sayit" / plat.lower() / fmt
    if app_tree.exists():
        shutil.rmtree(app_tree)
        print(f"[isolation] removed previous build tree: {app_tree}")


def stage_offline_models(project_root: Path, source: str | None) -> Path:
    """Stage + integrity-verify the four INT8 models into the source tree.

    Returns the staging destination. Raises (failing the build) on any missing
    file or hash/size mismatch via scripts/stage_bundled_models.py (which runs
    --clean, so the dir is rebuilt from scratch each time).
    """
    dest = project_root / STAGING_REL
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "stage_bundled_models.py"),
        "--dest",
        str(dest),
        "--clean",
    ]
    if source:
        cmd += ["--source", source]
    print("\n[offline] staging + verifying bundled models (integrity gate)...")
    subprocess.run(cmd, cwd=project_root, check=True)
    return dest


def packaged_app_models_dir(project_root: Path, plat: str) -> Path:
    """Path to resources/bundled_models inside the built app tree."""
    if plat == "windows":
        return (
            project_root
            / "build"
            / "sayit"
            / "windows"
            / "app"
            / "src"
            / "app"
            / "sayit"
            / "resources"
            / "bundled_models"
        )
    if plat == "macOS":
        # Briefcase macOS layout: build/sayit/macos/app/SayIt.app/Contents/
        #   Resources/app/sayit/resources/bundled_models
        found = next(
            (project_root / "build" / "sayit" / "macos" / "app").glob(
                "*.app/Contents/Resources/app/sayit/resources/bundled_models"
            ),
            None,
        )
        if found:
            return found
        # Fallback to the expected path even if the .app is not yet built, so
        # the offline copy step has a deterministic destination.
        return (
            project_root
            / "build"
            / "sayit"
            / "macos"
            / "app"
            / "SayIt.app"
            / "Contents"
            / "Resources"
            / "app"
            / "sayit"
            / "resources"
            / "bundled_models"
        )
    # Linux AppImage layout
    found = next(
        (project_root / "build" / "sayit" / "linux").glob(
            "*/*/usr/lib/sayit/app/sayit/resources/bundled_models"
        ),
        None,
    )
    return found or (
        project_root
        / "build"
        / "sayit"
        / "linux"
        / "sayit"
        / "resources"
        / "bundled_models"
    )


def copy_models_into_build(project_root: Path, plat: str) -> Path:
    """Ensure the staged models are present inside the built app tree.

    Briefcase copies the source package on create/update, but we also copy
    explicitly after build so the models are guaranteed to be in the packaged
    output regardless of Briefcase's incremental behaviour. Then re-verify in
    place as a final gate. Returns the packaged models dir.
    """
    staged = project_root / STAGING_REL
    app_pkg = packaged_app_models_dir(project_root, plat)

    if app_pkg.exists():
        shutil.rmtree(app_pkg)
    app_pkg.parent.mkdir(parents=True, exist_ok=True)
    print(f"[offline] copying staged models into build tree: {app_pkg}")
    shutil.copytree(staged, app_pkg)

    # Final in-place integrity gate on the packaged copy.
    from sayit.core.asr.models.model_integrity import verify_staged_models

    verify_staged_models(str(app_pkg))
    print("[offline] packaged-copy integrity gate: PASS")
    return app_pkg


# ---------------------------------------------------------------------------
# Pre-package validation gates (inspect the ACTUAL packaged app tree)
# ---------------------------------------------------------------------------
class BuildIsolationError(RuntimeError):
    """Raised when the packaged app tree does not match the requested variant."""


def _find_model_weight_files(root: Path) -> list[Path]:
    """All model weight files (.onnx) anywhere under ``root``."""
    if not root.exists():
        return []
    return sorted(root.rglob("*.onnx"))


def gate_offline_contents(project_root: Path, plat: str) -> None:
    """Fail unless the packaged app contains exactly the four approved models."""
    from sayit.core.asr.models.model_integrity import (
        load_bundled_manifest,
        verify_staged_models,
    )

    models_dir = packaged_app_models_dir(project_root, plat)
    if not models_dir.is_dir():
        raise BuildIsolationError(
            f"[offline gate] bundled_models dir missing in packaged app: {models_dir}"
        )

    manifest = load_bundled_manifest()
    expected_ids = {m.id for m in manifest}

    present_ids = {p.name for p in models_dir.iterdir() if p.is_dir()}
    missing = expected_ids - present_ids
    unexpected = present_ids - expected_ids
    if missing:
        raise BuildIsolationError(
            f"[offline gate] missing required model(s): {sorted(missing)}"
        )
    if unexpected:
        raise BuildIsolationError(
            f"[offline gate] unexpected model id(s) in bundle: {sorted(unexpected)}"
        )

    # Full hash/size/required-file verification of every model.
    verify_staged_models(str(models_dir))

    n_weights = len(_find_model_weight_files(models_dir))
    print(
        f"[offline gate] PASS: {len(expected_ids)} approved models, "
        f"{n_weights} weight files, all integrity-verified."
    )


def gate_ondemand_contents(project_root: Path, plat: str) -> None:
    """Fail if ANY bundled model weight leaked into the smaller app tree."""
    # Scan the whole app src tree, not just the (expected-absent) bundled dir.
    if plat == "windows":
        app_src = project_root / "build" / "sayit" / "windows" / "app" / "src"
    elif plat == "macOS":
        app_src = next(
            (project_root / "build" / "sayit" / "macos" / "app").glob(
                "*.app/Contents/Resources/app"
            ),
            project_root / "build" / "sayit" / "macos" / "app",
        )
    else:
        app_src = next(
            (project_root / "build" / "sayit" / "linux").glob("*/*/usr/lib/sayit"),
            project_root / "build" / "sayit" / "linux",
        )

    models_dir = packaged_app_models_dir(project_root, plat)
    if models_dir.exists():
        raise BuildIsolationError(
            f"[ondemand gate] bundled_models dir must NOT exist, found: {models_dir}"
        )

    # Any .onnx under the app package indicates leaked model weights. (The ASR
    # engine wheels do not ship .onnx weights; only bundled models would.)
    leaked = [
        p
        for p in _find_model_weight_files(app_src)
        if "bundled_models" in p.parts or "resources" in p.parts
    ]
    if leaked:
        raise BuildIsolationError(
            "[ondemand gate] bundled model weights leaked into smaller build: "
            + ", ".join(str(p) for p in leaked[:5])
        )
    print("[ondemand gate] PASS: no bundled model weights in the smaller app tree.")


def package_macos_dmg(project_root: Path, variant: str) -> None:
    """Package the built macOS .app into a DMG and rename per arch + variant.

    Signing/notarization are credential-gated: when ``SAYIT_MACOS_SIGN_IDENTITY``
    is set (a Developer ID Application identity), Briefcase signs; otherwise the
    build is ad-hoc/unsigned and clearly reported as NOT notarized. We never
    fabricate credentials or label an unsigned DMG as notarized.

    The DMG is renamed to SayIt-<arch>[-Offline].dmg so the arch + variant are
    unambiguous for the website manifest and users.
    """
    import platform as _platform

    identity = os.environ.get("SAYIT_MACOS_SIGN_IDENTITY", "").strip()
    cmd = [sys.executable, "-m", "briefcase", "package", "macOS", "app"]
    if identity:
        cmd += ["--identity", identity]
        print(f"[macOS] packaging DMG with signing identity: {identity[:12]}…")
    else:
        # No signing secret present -> produce an unsigned/adhoc DMG. This is a
        # development artifact; public distribution requires signing+notarization.
        cmd += ["--no-sign"]
        print(
            "[macOS] NO signing identity (SAYIT_MACOS_SIGN_IDENTITY unset): "
            "building UNSIGNED DMG. This is NOT notarized and not for public "
            "distribution."
        )
    subprocess.run(cmd, cwd=project_root, check=True)

    # Locate the produced DMG and rename with arch + variant.
    dist = project_root / "dist"
    dmgs = sorted(dist.glob("*.dmg")) if dist.is_dir() else []
    if not dmgs:
        print("[macOS] WARNING: no DMG found in dist/ after packaging.")
        return
    produced = dmgs[-1]
    machine = (_platform.machine() or "").lower()
    arch_tag = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    suffix = "-Offline" if variant == "offline" else ""
    target = dist / f"SayIt-macOS-{arch_tag}{suffix}.dmg"
    if produced != target:
        shutil.copy2(produced, target)
    print(f"[macOS] DMG ready: {target}")


def build(variant: str, source: str | None) -> None:
    project_root = PROJECT_ROOT
    plat, fmt = get_platform_target()

    app_version = os.environ.get("APP_VERSION")
    if app_version and app_version.startswith("v"):
        app_version = app_version[1:]
    if app_version:
        inject_version(project_root, app_version)

    # --- Build isolation: deterministic, order-independent starting state ----
    # Always start from a clean staging dir and a clean build tree so the
    # packaged output depends ONLY on the requested variant.
    clean_staging(project_root)
    clean_build_tree(project_root, plat, fmt)

    if variant == "offline":
        stage_offline_models(project_root, source)

    print("=" * 60)
    print(f"Briefcase Build - {plat} ({fmt}) - variant={variant}")
    print("=" * 60)

    try:
        generate_icons(project_root)
        print(f"\n[1/2] Creating application scaffold for {plat}/{fmt}...")
        subprocess.run(
            [sys.executable, "-m", "briefcase", "create", plat, fmt, "--no-input"],
            cwd=project_root,
            check=True,
        )
        print(f"\n[2/2] Building application for {plat}/{fmt}...")
        subprocess.run(
            [sys.executable, "-m", "briefcase", "build", plat, fmt],
            cwd=project_root,
            check=True,
        )

        if variant == "offline":
            copy_models_into_build(project_root, plat)

        # --- Pre-package validation gate (inspect the real packaged tree) ----
        if variant == "offline":
            gate_offline_contents(project_root, plat)
        else:
            gate_ondemand_contents(project_root, plat)

        print("\n" + "=" * 60)
        print(f"Build successful! (variant={variant})")
        print("=" * 60)
        if plat == "windows":
            print("Next: compile the installer with Inno Setup:")
            if variant == "offline":
                print(
                    "  ISCC.exe installer-offline.iss  -> SayIt-Setup-x64-Offline.exe"
                )
            else:
                print("  ISCC.exe installer.iss          -> SayIt-Setup-x64.exe")
        elif plat == "macOS":
            package_macos_dmg(project_root, variant)
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with exit code {e.returncode}")
        sys.exit(1)
    except BuildIsolationError as e:
        print(f"\nBUILD ISOLATION GATE FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--variant",
        choices=["ondemand", "offline"],
        default="ondemand",
        help="ondemand = download-on-demand (smaller); offline = bundle models",
    )
    ap.add_argument(
        "--source",
        default=None,
        help="Model source store for offline staging (default: user model cache)",
    )
    args = ap.parse_args()
    build(args.variant, args.source)


if __name__ == "__main__":
    main()
