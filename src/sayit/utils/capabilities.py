"""Platform capability layer for SayIt.

A single, narrow place that answers "what can this OS/session actually do?"
so the rest of the app never scatters ``sys.platform`` / ``os.environ`` checks.
Everything here is detection + policy only — it performs no dictation, never
touches application state, and prefers standard-library / already-present APIs.

Design rules:
- Pure, cheap, import-safe. No heavy imports at module load (pynput, Qt, D-Bus
  are only touched lazily by callers, not here).
- Honest: a capability reports ``available=False`` with an actionable reason
  rather than pretending a facility exists. The app must surface these reasons
  and never claim to be "listening/ready" when the OS denied access.
- Overridable for tests via environment variables documented on each helper.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# OS / architecture
# ---------------------------------------------------------------------------
class OS(str, Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


def current_os() -> OS:
    """Normalized OS. ``platform.system()`` maps Darwin -> macos."""
    system = platform.system().lower()
    if system == "windows":
        return OS.WINDOWS
    if system == "darwin":
        return OS.MACOS
    if system == "linux":
        return OS.LINUX
    return OS.UNKNOWN


def is_windows() -> bool:
    return current_os() is OS.WINDOWS


def is_macos() -> bool:
    return current_os() is OS.MACOS


def is_linux() -> bool:
    return current_os() is OS.LINUX


def arch() -> str:
    """Normalized CPU architecture token: 'arm64', 'x86_64', or machine()."""
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64", "x64"):
        return "x86_64"
    return m or "unknown"


# ---------------------------------------------------------------------------
# Linux display session (X11 vs Wayland)
# ---------------------------------------------------------------------------
class DisplaySession(str, Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"
    NA = "n/a"  # not Linux


def display_session() -> DisplaySession:
    """Detect the Linux display server session.

    Uses ``XDG_SESSION_TYPE`` first, then the presence of ``WAYLAND_DISPLAY`` /
    ``DISPLAY``. Returns ``NA`` off Linux. Honest about "unknown" rather than
    guessing — callers decide the fallback.
    """
    if not is_linux():
        return DisplaySession.NA
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session == "wayland":
        return DisplaySession.WAYLAND
    if session == "x11":
        return DisplaySession.X11
    # Fall back to the display sockets.
    if os.environ.get("WAYLAND_DISPLAY"):
        return DisplaySession.WAYLAND
    if os.environ.get("DISPLAY"):
        return DisplaySession.X11
    return DisplaySession.UNKNOWN


# ---------------------------------------------------------------------------
# Hotkey backend selection
# ---------------------------------------------------------------------------
class HotkeyBackend(str, Enum):
    PYNPUT = "pynput"  # Windows, macOS, Linux/X11
    WAYLAND_PORTAL = "wayland_portal"  # Linux/Wayland GlobalShortcuts portal
    NONE = "none"  # no supported backend in this environment


def hotkey_backend() -> HotkeyBackend:
    """Choose the global-hotkey backend for the current OS/session.

    - Windows / macOS: pynput (macOS additionally requires Accessibility /
      Input Monitoring permission — reported separately).
    - Linux X11: pynput.
    - Linux Wayland: the XDG ``GlobalShortcuts`` portal (pynput cannot receive
      arbitrary global keys under Wayland). Falls back to pynput only when a
      Wayland session is actually running an X11-compatible listener (Xwayland
      is NOT treated as real Wayland support).
    - Unknown Linux session: pynput is attempted but may fail; the app surfaces
      the failure rather than claiming success.

    Overridable with ``SAYIT_HOTKEY_BACKEND`` (pynput|wayland_portal|none).
    """
    override = os.environ.get("SAYIT_HOTKEY_BACKEND", "").strip().lower()
    if override in (b.value for b in HotkeyBackend):
        return HotkeyBackend(override)

    os_ = current_os()
    if os_ in (OS.WINDOWS, OS.MACOS):
        return HotkeyBackend.PYNPUT
    if os_ is OS.LINUX:
        session = display_session()
        if session is DisplaySession.WAYLAND:
            return HotkeyBackend.WAYLAND_PORTAL
        # X11 or unknown -> try pynput (X11 path).
        return HotkeyBackend.PYNPUT
    return HotkeyBackend.NONE


# ---------------------------------------------------------------------------
# Text insertion (paste) semantics
# ---------------------------------------------------------------------------
def paste_modifier() -> str:
    """The modifier used for the paste keystroke: 'cmd' on macOS, else 'ctrl'."""
    return "cmd" if is_macos() else "ctrl"


# ---------------------------------------------------------------------------
# Clipboard backend (Linux needs an external tool; others are built-in)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClipboardCapability:
    available: bool
    backend: str  # "windows" | "pbcopy" | "wl-clipboard" | "xclip" | "xsel" | "none"
    reason: str = ""  # actionable guidance when unavailable


def clipboard_capability() -> ClipboardCapability:
    """Detect a working clipboard backend.

    Windows/macOS use the OS-native clipboard (pyperclip: win32 API / pbcopy),
    always available. Linux needs an external tool: ``wl-clipboard`` (wl-copy)
    on Wayland, or ``xclip``/``xsel`` on X11. When none is installed we report
    an actionable install hint instead of silently failing at paste time.
    """
    if is_windows():
        return ClipboardCapability(True, "windows")
    if is_macos():
        # pbcopy/pbpaste ship with macOS.
        return ClipboardCapability(True, "pbcopy")
    if is_linux():
        session = display_session()
        if session is DisplaySession.WAYLAND and shutil.which("wl-copy"):
            return ClipboardCapability(True, "wl-clipboard")
        if shutil.which("xclip"):
            return ClipboardCapability(True, "xclip")
        if shutil.which("xsel"):
            return ClipboardCapability(True, "xsel")
        # Nothing found — give the user the exact package to install.
        if session is DisplaySession.WAYLAND:
            hint = "Install 'wl-clipboard' (e.g. sudo apt install wl-clipboard)."
        else:
            hint = "Install 'xclip' or 'xsel' (e.g. sudo apt install xclip)."
        return ClipboardCapability(False, "none", hint)
    return ClipboardCapability(False, "none", "Unsupported OS for clipboard.")


# ---------------------------------------------------------------------------
# Automatic insertion (synthetic paste keystroke) capability
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InsertionCapability:
    # Whether an automatic paste keystroke can be *attempted*. Even when True,
    # paste completion is never confirmable (see InsertionResult); when False
    # the app must fall back to leaving the transcript on the clipboard.
    auto_insert: bool
    reason: str = ""


def insertion_capability() -> InsertionCapability:
    """Whether desktop-wide synthetic paste can be attempted.

    - Windows / macOS: yes (macOS also needs Accessibility permission to
      actually deliver the keystroke; that is reported by permission checks).
    - Linux X11: yes (pynput/XTEST).
    - Linux Wayland: synthetic input is restricted by the compositor. We do NOT
      claim automatic insertion here; the honest fallback is to leave the
      transcript on the clipboard and tell the user to paste. Overridable with
      ``SAYIT_FORCE_WAYLAND_INSERT=1`` for environments known to allow it.
    """
    if is_windows() or is_macos():
        return InsertionCapability(True)
    if is_linux():
        session = display_session()
        if session is DisplaySession.WAYLAND and os.environ.get(
            "SAYIT_FORCE_WAYLAND_INSERT", ""
        ) != "1":
            return InsertionCapability(
                False,
                "Wayland restricts synthetic keystrokes; the transcript will be "
                "placed on the clipboard for you to paste (Ctrl+V).",
            )
        return InsertionCapability(True)
    return InsertionCapability(False, "Unsupported OS for text insertion.")


# ---------------------------------------------------------------------------
# System tray availability
# ---------------------------------------------------------------------------
def tray_available() -> bool:
    """Whether a system tray / menu-bar item can be shown.

    Uses Qt's own check when a QApplication exists. Off-Linux this is virtually
    always True; on Linux it depends on a StatusNotifierItem host being present.
    Returns True when Qt is not yet initialized (optimistic; the app re-checks
    at tray-creation time and falls back if creation fails).
    """
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon

        if QApplication.instance() is None:
            return True
        return bool(QSystemTrayIcon.isSystemTrayAvailable())
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Microphone / permission diagnostics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PermissionStatus:
    # Tri-state: True granted, False denied, None unknown/not-determinable.
    granted: Optional[bool]
    reason: str = ""


def microphone_permission() -> PermissionStatus:
    """Best-effort microphone-permission status.

    There is no portable, synchronous permission API. We return ``None``
    (unknown) by default; the real signal is whether the audio stream opens
    (the recorder surfaces a denial message). On macOS the first stream open
    triggers the OS prompt. Overridable for tests with
    ``SAYIT_MIC_PERMISSION`` in {granted,denied,unknown}.
    """
    override = os.environ.get("SAYIT_MIC_PERMISSION", "").strip().lower()
    if override == "granted":
        return PermissionStatus(True)
    if override == "denied":
        return PermissionStatus(
            False, macos_privacy_hint("Microphone") if is_macos() else
            "Microphone access is denied; grant it in your OS privacy settings."
        )
    return PermissionStatus(None)


def accessibility_permission() -> PermissionStatus:
    """macOS Accessibility / Input-Monitoring status for global key monitoring.

    Determined at runtime from pynput's ``IS_TRUSTED`` once a listener exists
    (the hotkey layer reports it). Here we only answer the static question:
    is this permission *required*? On macOS global keyboard monitoring and
    synthetic key input require it; elsewhere it is not applicable.
    """
    if not is_macos():
        return PermissionStatus(True)  # not required off macOS
    return PermissionStatus(
        None,
        macos_privacy_hint("Accessibility / Input Monitoring")
        + " Required for the global hotkey and for inserting text into other apps.",
    )


def macos_privacy_hint(pane: str) -> str:
    return (
        f"Open System Settings > Privacy & Security > {pane}, enable SayIt, then "
        "restart SayIt."
    )


# ---------------------------------------------------------------------------
# Consolidated diagnostics (for the setup wizard / error surfaces)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CapabilityReport:
    os: str
    arch: str
    display_session: str
    hotkey_backend: str
    clipboard: ClipboardCapability
    insertion: InsertionCapability
    tray: bool
    paste_modifier: str


def capability_report() -> CapabilityReport:
    """A single snapshot the UI can render for diagnostics. Side-effect free."""
    return CapabilityReport(
        os=current_os().value,
        arch=arch(),
        display_session=display_session().value,
        hotkey_backend=hotkey_backend().value,
        clipboard=clipboard_capability(),
        insertion=insertion_capability(),
        tray=tray_available(),
        paste_modifier=paste_modifier(),
    )
