"""Tests for the platform capability layer (cross-platform).

These exercise every OS/session branch deterministically by monkeypatching the
``capabilities`` primitives and environment, so the same suite validates the
Windows, macOS, and Linux(X11/Wayland) policies from any host.
"""

from __future__ import annotations

import sayit.utils.capabilities as caps


# --- OS / arch --------------------------------------------------------------
def test_current_os_maps_darwin_to_macos(monkeypatch):
    monkeypatch.setattr(caps.platform, "system", lambda: "Darwin")
    assert caps.current_os() is caps.OS.MACOS
    assert caps.is_macos() and not caps.is_windows() and not caps.is_linux()


def test_current_os_windows_linux(monkeypatch):
    monkeypatch.setattr(caps.platform, "system", lambda: "Windows")
    assert caps.current_os() is caps.OS.WINDOWS
    monkeypatch.setattr(caps.platform, "system", lambda: "Linux")
    assert caps.current_os() is caps.OS.LINUX


def test_arch_normalization(monkeypatch):
    for raw, norm in (("arm64", "arm64"), ("aarch64", "arm64"),
                      ("x86_64", "x86_64"), ("AMD64", "x86_64")):
        monkeypatch.setattr(caps.platform, "machine", lambda r=raw: r)
        assert caps.arch() == norm


# --- display session --------------------------------------------------------
def test_display_session_wayland_x11_unknown(monkeypatch):
    monkeypatch.setattr(caps, "current_os", lambda: caps.OS.LINUX)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert caps.display_session() is caps.DisplaySession.WAYLAND
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert caps.display_session() is caps.DisplaySession.X11
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert caps.display_session() is caps.DisplaySession.X11
    monkeypatch.delenv("DISPLAY", raising=False)
    assert caps.display_session() is caps.DisplaySession.UNKNOWN


def test_display_session_na_off_linux(monkeypatch):
    monkeypatch.setattr(caps, "current_os", lambda: caps.OS.WINDOWS)
    assert caps.display_session() is caps.DisplaySession.NA


# --- hotkey backend ---------------------------------------------------------
def test_hotkey_backend_per_os(monkeypatch):
    monkeypatch.delenv("SAYIT_HOTKEY_BACKEND", raising=False)
    monkeypatch.setattr(caps, "current_os", lambda: caps.OS.WINDOWS)
    assert caps.hotkey_backend() is caps.HotkeyBackend.PYNPUT
    monkeypatch.setattr(caps, "current_os", lambda: caps.OS.MACOS)
    assert caps.hotkey_backend() is caps.HotkeyBackend.PYNPUT
    monkeypatch.setattr(caps, "current_os", lambda: caps.OS.LINUX)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.X11)
    assert caps.hotkey_backend() is caps.HotkeyBackend.PYNPUT
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.WAYLAND)
    assert caps.hotkey_backend() is caps.HotkeyBackend.WAYLAND_PORTAL


def test_hotkey_backend_override(monkeypatch):
    monkeypatch.setenv("SAYIT_HOTKEY_BACKEND", "none")
    assert caps.hotkey_backend() is caps.HotkeyBackend.NONE


# --- paste modifier ---------------------------------------------------------
def test_paste_modifier_cmd_on_macos(monkeypatch):
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    assert caps.paste_modifier() == "cmd"
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    assert caps.paste_modifier() == "ctrl"


# --- clipboard capability ---------------------------------------------------
def test_clipboard_windows_macos_builtin(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: True)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: False)
    assert caps.clipboard_capability().available
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    c = caps.clipboard_capability()
    assert c.available and c.backend == "pbcopy"


def test_clipboard_linux_wayland_prefers_wl(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: True)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.WAYLAND)
    monkeypatch.setattr(caps.shutil, "which", lambda t: "/usr/bin/wl-copy" if t == "wl-copy" else None)
    c = caps.clipboard_capability()
    assert c.available and c.backend == "wl-clipboard"


def test_clipboard_linux_x11_xclip_then_xsel(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: True)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.X11)
    monkeypatch.setattr(caps.shutil, "which", lambda t: "/usr/bin/xclip" if t == "xclip" else None)
    assert caps.clipboard_capability().backend == "xclip"
    monkeypatch.setattr(caps.shutil, "which", lambda t: "/usr/bin/xsel" if t == "xsel" else None)
    assert caps.clipboard_capability().backend == "xsel"


def test_clipboard_linux_none_gives_install_hint(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: True)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.WAYLAND)
    monkeypatch.setattr(caps.shutil, "which", lambda t: None)
    c = caps.clipboard_capability()
    assert not c.available
    assert "wl-clipboard" in c.reason


# --- insertion capability ---------------------------------------------------
def test_insertion_wayland_blocks_auto_insert(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: True)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.WAYLAND)
    monkeypatch.delenv("SAYIT_FORCE_WAYLAND_INSERT", raising=False)
    cap = caps.insertion_capability()
    assert cap.auto_insert is False
    assert "clipboard" in cap.reason.lower()


def test_insertion_wayland_force_override(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    monkeypatch.setattr(caps, "is_linux", lambda: True)
    monkeypatch.setattr(caps, "display_session", lambda: caps.DisplaySession.WAYLAND)
    monkeypatch.setenv("SAYIT_FORCE_WAYLAND_INSERT", "1")
    assert caps.insertion_capability().auto_insert is True


def test_insertion_x11_and_desktop_os_allow(monkeypatch):
    monkeypatch.setattr(caps, "is_windows", lambda: True)
    assert caps.insertion_capability().auto_insert is True
    monkeypatch.setattr(caps, "is_windows", lambda: False)
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    assert caps.insertion_capability().auto_insert is True


# --- permissions ------------------------------------------------------------
def test_microphone_permission_override(monkeypatch):
    monkeypatch.setenv("SAYIT_MIC_PERMISSION", "denied")
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    st = caps.microphone_permission()
    assert st.granted is False and "Privacy" in st.reason
    monkeypatch.setenv("SAYIT_MIC_PERMISSION", "granted")
    assert caps.microphone_permission().granted is True
    monkeypatch.setenv("SAYIT_MIC_PERMISSION", "unknown")
    assert caps.microphone_permission().granted is None


def test_accessibility_required_only_on_macos(monkeypatch):
    monkeypatch.setattr(caps, "is_macos", lambda: False)
    assert caps.accessibility_permission().granted is True
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    st = caps.accessibility_permission()
    assert st.granted is None and "Accessibility" in st.reason


# --- report -----------------------------------------------------------------
def test_capability_report_snapshot():
    rep = caps.capability_report()
    assert rep.os in ("windows", "macos", "linux", "unknown")
    assert rep.paste_modifier in ("cmd", "ctrl")
    # Shape only — values depend on the host.
    assert hasattr(rep.clipboard, "available")
    assert hasattr(rep.insertion, "auto_insert")
