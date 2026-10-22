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


def _dir_size_bytes(path: Path) -> int:
    """Total on-disk size of all files under ``path`` (follows the tree, not
    symlinks). Used to measure the completed .app payload for DMG sizing."""
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_symlink():
                # Count the link entry itself, not its (possibly external) target.
                total += p.lstat().st_size
            elif p.is_file():
                total += p.stat().st_size
        except OSError:
            # A file that vanished mid-walk should not crash sizing.
            continue
    return total


def compute_dmg_capacity_bytes(app_payload_bytes: int) -> int:
    """Compute the writable DMG image capacity (bytes) for an ``.app`` payload.

    The capacity must exceed the raw payload because an HFS+/APFS image carries
    filesystem overhead (catalog, allocation bitmap, journal) and the packaging
    operations (``ditto`` copy + the ``/Applications`` symlink + volume icon /
    ``.DS_Store`` layout) need working headroom. dmgbuild 1.6.6 under Briefcase
    0.3.26 under-sizes the image for a large model-bundling payload (~1.33 GiB),
    so we size the image ourselves from the MEASURED payload.

    Rule: 30% headroom, with a minimum absolute floor of 64 MiB of slack so even
    tiny (online) bundles always fit. Raises ``ValueError`` on a non-positive /
    invalid payload so an empty or failed build never yields a bogus image.
    """
    if not isinstance(app_payload_bytes, int) or app_payload_bytes <= 0:
        raise ValueError(
            f"invalid .app payload size for DMG sizing: {app_payload_bytes!r}"
        )
    mib = 1024 * 1024
    headroom = max(int(app_payload_bytes * 0.30), 64 * mib)
    capacity = app_payload_bytes + headroom
    # Round up to a whole MiB; hdiutil accepts a byte size but whole MiB is tidy.
    capacity = ((capacity + mib - 1) // mib) * mib
    if capacity <= app_payload_bytes:
        # Defensive: never return a capacity that cannot hold the payload.
        raise ValueError(
            f"computed DMG capacity {capacity} <= payload {app_payload_bytes}"
        )
    return capacity


def _hdiutil_detach(target: str, attempts: int = 6) -> bool:
    """Detach an attached DMG image, tolerating DiskArbitration lag.

    ``hdiutil convert`` fails with "Resource temporarily unavailable" if the
    writable image is still attached, and a detach immediately after a large
    ``ditto`` can report "timeout for DiskArbitration expired / drive not
    detached". Retry: plain detach first, then ``-force``, with a short settle
    between tries. Returns True once the target is released.
    """
    import time as _time

    for i in range(attempts):
        flags = ["-force"] if i > 0 else []
        r = subprocess.run(
            ["hdiutil", "detach", target, *flags],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return True
        # If hdiutil says it's already not attached, treat as success.
        combined = (r.stdout + r.stderr).lower()
        if "no such file" in combined or "not attached" in combined:
            return True
        _time.sleep(2.0 * (i + 1))
    print(f"[macOS dmg] WARNING: could not confirm detach of {target}")
    return False


def _make_dmg_hdiutil(app_path: Path, out_dmg: Path, volume_name: str) -> None:
    """Build a compressed, read-only DMG from a (already-signed) ``.app`` using
    macOS-native ``hdiutil``, sized from the actual payload.

    Steps:
      1. Measure the completed .app payload and compute a sufficient capacity.
      2. Create a writable UDRW image of that capacity (``hdiutil create``).
      3. Attach it, ``ditto`` the .app in WITHOUT modifying its contents (so the
         code signature stays valid), add the ``/Applications`` shortcut to
         preserve the drag-to-install layout, then detach.
      4. Convert the writable image to a compressed read-only UDZO DMG.
      5. Verify the DMG mounts and contains the complete ``.app``.

    Never mutates the signed .app. Raises ``RuntimeError`` with a clear
    diagnostic if any step fails or the capacity cannot hold the payload.
    """
    import tempfile

    if not app_path.is_dir():
        raise RuntimeError(f"[macOS dmg] .app not found: {app_path}")

    payload = _dir_size_bytes(app_path)
    capacity = compute_dmg_capacity_bytes(payload)
    print(
        f"[macOS dmg] payload={payload / (1024*1024):.1f} MiB -> "
        f"image capacity={capacity / (1024*1024):.1f} MiB "
        f"(payload + max(30%, 64 MiB) headroom)"
    )

    out_dmg.parent.mkdir(parents=True, exist_ok=True)
    if out_dmg.exists():
        out_dmg.unlink()

    with tempfile.TemporaryDirectory() as td:
        rw_dmg = Path(td) / "sayit-rw.dmg"
        # 1) Create a writable image sized to our computed capacity.
        subprocess.run(
            [
                "hdiutil", "create",
                "-size", str(capacity),
                "-fs", "HFS+",
                "-volname", volume_name,
                "-type", "UDIF",
                str(rw_dmg),
            ],
            check=True,
        )
        # 2) Attach (no auto-open, no Finder browse). Capture BOTH the device
        #    node and the mount point from the attach table: detaching by the
        #    device node is more reliable than by mount point.
        attach = subprocess.run(
            [
                "hdiutil", "attach", str(rw_dmg),
                "-nobrowse", "-noautoopen", "-owners", "on",
            ],
            check=True, capture_output=True, text=True,
        )
        mount_point = None
        device_node = None
        for line in attach.stdout.splitlines():
            parts = line.split("\t")
            if parts and parts[0].strip().startswith("/dev/") and device_node is None:
                device_node = parts[0].strip()
            if "/Volumes/" in line:
                mount_point = "/Volumes/" + line.split("/Volumes/", 1)[1].strip()
        if not mount_point:
            raise RuntimeError(
                f"[macOS dmg] could not determine mount point:\n{attach.stdout}"
            )
        detached = False
        try:
            mp = Path(mount_point)
            # 3) Copy the signed .app verbatim (ditto preserves metadata +
            #    extended attributes, so the code signature remains valid).
            subprocess.run(
                ["ditto", str(app_path), str(mp / app_path.name)], check=True
            )
            # Preserve the drag-to-install layout: an /Applications shortcut.
            app_link = mp / "Applications"
            if not app_link.exists():
                os.symlink("/Applications", app_link)
            # Flush writes before detaching so convert sees a quiescent image.
            subprocess.run(["sync"], check=False)
            # 4a) Detach the WRITABLE image fully BEFORE converting. A lingering
            #     DiskArbitration reference makes `convert` fail with "Resource
            #     temporarily unavailable", so detach with retries by device
            #     node (falling back to the mount point) and confirm release.
            detached = _hdiutil_detach(device_node or mount_point)
        finally:
            if not detached:
                # Best-effort final detach if the normal path failed/raised.
                _hdiutil_detach(device_node or mount_point, attempts=3)
        # 4b) Convert the now-detached writable image to a compressed,
        #     read-only distributable DMG.
        subprocess.run(
            [
                "hdiutil", "convert", str(rw_dmg),
                "-format", "UDZO", "-imagekey", "zlib-level=9",
                "-o", str(out_dmg),
            ],
            check=True,
        )

    # 5) Verify the output DMG mounts and contains the complete .app.
    verify = subprocess.run(
        ["hdiutil", "attach", str(out_dmg), "-nobrowse", "-noautoopen", "-readonly"],
        check=True, capture_output=True, text=True,
    )
    vmount = None
    vdev = None
    for line in verify.stdout.splitlines():
        parts = line.split("\t")
        if parts and parts[0].strip().startswith("/dev/") and vdev is None:
            vdev = parts[0].strip()
        if "/Volumes/" in line:
            vmount = "/Volumes/" + line.split("/Volumes/", 1)[1].strip()
    try:
        if not vmount:
            raise RuntimeError("[macOS dmg] verification mount failed")
        copied_app = Path(vmount) / app_path.name
        if not (copied_app / "Contents" / "MacOS").is_dir():
            raise RuntimeError(
                f"[macOS dmg] verification: {copied_app} missing Contents/MacOS"
            )
        copied_size = _dir_size_bytes(copied_app)
        # The copied payload must match the source within a small tolerance
        # (ditto is a faithful copy; allow 1% for FS metadata differences).
        if copied_size < payload * 0.99:
            raise RuntimeError(
                f"[macOS dmg] verification: copied payload {copied_size} < "
                f"source {payload} (incomplete copy)"
            )
        print(
            f"[macOS dmg] verified: {out_dmg.name} mounts and contains "
            f"{app_path.name} ({copied_size / (1024*1024):.1f} MiB)"
        )
    finally:
        if vdev or vmount:
            _hdiutil_detach(vdev or vmount, attempts=4)


def package_macos_dmg(project_root: Path, variant: str) -> None:
    """Package the built macOS .app into a DMG and rename per arch + variant.

    Two-stage, to avoid dmgbuild under-sizing the image for the model-bundling
    offline bundle (~1.33 GiB), which failed with "No space left on device":

      1. ``briefcase package macOS app -p zip`` SIGNS the .app (ad-hoc when no
         identity, Developer ID when ``SAYIT_MACOS_SIGN_IDENTITY`` is set) and
         produces a zipped .app — WITHOUT invoking dmgbuild. Signing semantics
         are unchanged.
      2. A payload-sized ``hdiutil`` helper builds the DMG from the already-
         signed .app (ditto preserves the signature), preserving the
         /Applications drag-install layout, then compresses it read-only and
         verifies it mounts with the complete .app.

    Signing/notarization stay credential-gated and are never fabricated. The DMG
    is named SayIt-macOS-<arch>[-Offline].dmg for the website manifest + users.
    """
    import platform as _platform

    identity = os.environ.get("SAYIT_MACOS_SIGN_IDENTITY", "").strip()
    # Package as a signed, zipped .app (NO dmgbuild). --no-input: never block on
    # an interactive prompt on a headless CI runner.
    cmd = [
        sys.executable, "-m", "briefcase", "package", "macOS", "app",
        "--no-input", "--packaging-format", "zip",
    ]
    if identity:
        cmd += ["--identity", identity]
        print(f"[macOS] signing .app with Developer ID identity: {identity[:12]}…")
    else:
        # No signing secret present -> ad-hoc sign. The correct Briefcase flag
        # for an unsigned/ad-hoc package is ``--adhoc-sign`` (``--no-sign`` is
        # not a valid option and causes an interactive-prompt abort on CI).
        cmd += ["--adhoc-sign"]
        print(
            "[macOS] NO signing identity (SAYIT_MACOS_SIGN_IDENTITY unset): "
            "ad-hoc signing .app. The resulting DMG is UNSIGNED/NOT notarized "
            "and not for public distribution."
        )
    subprocess.run(cmd, cwd=project_root, check=True)

    # Locate the signed .app that Briefcase built + signed.
    app_glob = sorted(
        (project_root / "build" / "sayit" / "macos" / "app").glob("*.app")
    )
    if not app_glob:
        raise RuntimeError(
            "[macOS] no signed .app found under build/sayit/macos/app after "
            "briefcase package"
        )
    app_path = app_glob[0]

    machine = (_platform.machine() or "").lower()
    arch_tag = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    suffix = "-Offline" if variant == "offline" else ""
    dist = project_root / "dist"
    target = dist / f"SayIt-macOS-{arch_tag}{suffix}.dmg"

    # Build the payload-sized DMG from the signed .app (dmgbuild not used).
    _make_dmg_hdiutil(app_path, target, volume_name="SayIt")
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
