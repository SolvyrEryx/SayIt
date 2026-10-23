"""Regression tests for the Windows installer shortcut AppUserModelID (AUMID).

Root cause of the "reminder fires but no Windows notification appears" bug when
running the PACKAGED app: the Start Menu / desktop / startup shortcuts created
by the Inno Setup installer carried NO ``System.AppUserModel.ID``. The process
sets an explicit AUMID (``WINDOWS_APP_USER_MODEL_ID``) via
``SetCurrentProcessExplicitAppUserModelID``, but Windows only delivers a
toast/balloon to that identity when the LAUNCHING shortcut's AUMID matches the
process AUMID. With a mismatch (or a missing shortcut AUMID), the shell silently
suppresses the toast while ``QSystemTrayIcon.showMessage()`` still returns
without error.

These tests pin the fix at the source level (no Inno Setup / Windows required):

* Each installer declares ``#define MyAppUserModelID`` and it equals the
  process constant ``WINDOWS_APP_USER_MODEL_ID`` *exactly*.
* Every shortcut that LAUNCHES the app (Start Menu, desktop, startup) carries
  ``AppUserModelID: "{#MyAppUserModelID}"``.
* The uninstaller shortcut (which does not launch the app) is NOT given an
  AUMID, so we don't mislabel an unrelated shortcut.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLERS = ("installer.iss", "installer-offline.iss")


def _process_aumid() -> str:
    """Read ``WINDOWS_APP_USER_MODEL_ID`` straight from app.py source.

    Parsing the literal avoids importing the full Qt application (and its
    heavyweight/platform dependencies) just to read one constant.
    """
    src = (ROOT / "src" / "sayit" / "app.py").read_text(encoding="utf-8")
    m = re.search(
        r'^WINDOWS_APP_USER_MODEL_ID\s*=\s*"([^"]+)"', src, flags=re.MULTILINE
    )
    assert m, "WINDOWS_APP_USER_MODEL_ID not found in src/sayit/app.py"
    return m.group(1)


def _installer_define(text: str) -> str:
    m = re.search(r'^#define\s+MyAppUserModelID\s+"([^"]+)"', text, flags=re.MULTILINE)
    assert m, "MyAppUserModelID define not found in installer script"
    return m.group(1)


def _icons_lines(text: str) -> list[str]:
    """Return the shortcut definition lines from the [Icons] section."""
    lines = text.splitlines()
    out: list[str] = []
    in_icons = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_icons = stripped.lower() == "[icons]"
            continue
        if in_icons and stripped.startswith("Name:"):
            out.append(stripped)
    return out


def test_process_aumid_is_the_expected_identity():
    # Guards against an accidental rename on one side only.
    assert _process_aumid() == "VptrCipher.SayIt"


@pytest.mark.parametrize("name", INSTALLERS)
def test_installer_define_matches_process_aumid(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert _installer_define(text) == _process_aumid(), (
        f"{name}: shortcut AUMID define must match the process AUMID exactly, "
        "or Windows will suppress reminder toasts for the packaged app."
    )


@pytest.mark.parametrize("name", INSTALLERS)
def test_app_launching_shortcuts_carry_aumid(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    icon_lines = _icons_lines(text)
    assert icon_lines, f"{name}: no [Icons] entries found"

    # Shortcuts that launch the app resolve to the app executable; the
    # uninstaller shortcut resolves to {uninstallexe}.
    launching = [ln for ln in icon_lines if "{#MyAppExeName}" in ln]
    uninstall = [ln for ln in icon_lines if "{uninstallexe}" in ln]

    assert launching, f"{name}: expected at least one app-launching shortcut"
    for ln in launching:
        assert 'AppUserModelID: "{#MyAppUserModelID}"' in ln, (
            f"{name}: app-launching shortcut is missing the AUMID property; "
            f"Windows reminder notifications will be silently dropped:\n{ln}"
        )

    # The uninstaller shortcut must NOT claim the app identity.
    for ln in uninstall:
        assert (
            "AppUserModelID" not in ln
        ), f"{name}: the uninstaller shortcut should not carry an AUMID:\n{ln}"


@pytest.mark.parametrize("name", INSTALLERS)
def test_all_three_launch_targets_are_covered(name):
    """Start Menu, desktop, and startup shortcuts must each set the AUMID.

    If a new launch surface is added without an AUMID, reminders would work from
    some entry points but not others — a confusing partial failure.
    """
    text = (ROOT / name).read_text(encoding="utf-8")
    for target in ("{group}\\", "{autodesktop}\\", "{userstartup}\\"):
        pattern = re.compile(
            re.escape(target) + r'.*AppUserModelID: "\{#MyAppUserModelID\}"'
        )
        matching = [ln for ln in _icons_lines(text) if pattern.search(ln)]
        assert (
            matching
        ), f"{name}: expected an app shortcut under {target} carrying the AUMID"


def test_installer_preserves_exact_production_appid_default():
    """The QA-override templating must NOT change the production AppId.

    installer.iss now allows an isolated QA build to pass /DMyAppIdOverride, but
    the default (no override) branch MUST still emit the exact original AppId
    literal, or a production install would register under a different key and
    break in-place upgrades.
    """
    text = (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert "AppId={{13AD1DC3-955C-4618-86E0-36B01ABF13EF}}" in text
    # The override hook must exist so QA builds can isolate themselves.
    assert "#ifdef MyAppIdOverride" in text
    assert "AppId={#MyAppIdOverride}" in text


@pytest.mark.parametrize("name", INSTALLERS)
def test_installer_preserves_production_appid_and_override_hook(name):
    """Both installers keep the EXACT production AppId as the default branch and
    expose the /DMyAppIdOverride hook for isolated QA builds. Offline and
    on-demand MUST share the same production AppId (same product, in-place
    upgrade)."""
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "AppId={{13AD1DC3-955C-4618-86E0-36B01ABF13EF}}" in text
    assert "#ifdef MyAppIdOverride" in text
    assert "AppId={#MyAppIdOverride}" in text


def test_installer_install_name_defaults_to_app_name():
    """MyInstallName defaults to MyAppName so production shortcuts/dir/group are
    unchanged; only an explicit /DMyInstallName (QA) relabels them."""
    text = (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert "#ifndef MyInstallName" in text
    assert "#define MyInstallName MyAppName" in text


@pytest.mark.parametrize("name", INSTALLERS)
def test_installer_install_name_default_both(name):
    """Both installers default MyInstallName to MyAppName (production unchanged)."""
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "#ifndef MyInstallName" in text
    assert "#define MyInstallName MyAppName" in text
