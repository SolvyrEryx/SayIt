"""Wayland GlobalShortcuts portal backend tests.

The real portal handshake needs a live Wayland session + user interaction
(manual acceptance). Here we verify the honest detection + graceful fallback
contract deterministically, which is what guards the app's behaviour:
- availability is overridable and reported with a reason;
- start() returns False (never raises) when the portal is unavailable;
- the module imports safely on any OS (no hard dbus dependency at import).
"""

from __future__ import annotations

import importlib

import sayit.core.input.hotkey_wayland as wl


def test_module_imports_without_dbus():
    # Re-import to ensure top-level import never requires python-dbus.
    importlib.reload(wl)
    assert hasattr(wl, "WaylandPortalHotkey")
    assert hasattr(wl, "portal_available")


def test_portal_available_override(monkeypatch):
    monkeypatch.setenv("SAYIT_PORTAL_AVAILABLE", "1")
    assert wl.portal_available().available is True
    monkeypatch.setenv("SAYIT_PORTAL_AVAILABLE", "0")
    a = wl.portal_available()
    assert a.available is False and a.reason


def test_portal_available_no_dbus_reports_reason(monkeypatch):
    monkeypatch.delenv("SAYIT_PORTAL_AVAILABLE", raising=False)
    monkeypatch.setattr(wl, "_dbus_module", lambda: None)
    a = wl.portal_available()
    assert a.available is False
    assert "dbus" in a.reason.lower()


def test_start_returns_false_when_unavailable(monkeypatch):
    monkeypatch.setenv("SAYIT_PORTAL_AVAILABLE", "0")
    pressed, released = [], []
    hk = wl.WaylandPortalHotkey(lambda: pressed.append(1), lambda: released.append(1))
    assert hk.start() is False
    assert hk.is_running is False
    assert hk.last_reason  # actionable reason recorded
    # Callbacks never fired (no fake "listening").
    assert pressed == [] and released == []


def test_available_sets_last_reason(monkeypatch):
    monkeypatch.setenv("SAYIT_PORTAL_AVAILABLE", "0")
    hk = wl.WaylandPortalHotkey(lambda: None, lambda: None)
    assert hk.available() is False
    assert "disabled" in hk.last_reason.lower() or hk.last_reason
