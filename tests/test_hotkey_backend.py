"""Hotkey backend-selection + permission-diagnostic tests (cross-platform).

Validates that HotkeyListener consults the capability layer to pick a backend,
surfaces an actionable message (never silently switches keys) on Wayland/none,
and exposes macOS Accessibility trust — all without a real OS keyboard hook.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sayit.core.input.hotkey as hk  # noqa: E402
import sayit.utils.capabilities as caps  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def test_backend_reported_from_capabilities(monkeypatch):
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.PYNPUT)
    hl = hk.HotkeyListener()
    assert hl.backend == "pynput"


def test_wayland_backend_emits_unavailable_and_does_not_start(monkeypatch):
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.WAYLAND_PORTAL)
    hl = hk.HotkeyListener()
    captured = []
    hl.backend_unavailable.connect(lambda m: captured.append(m))
    hl.start()
    assert hl._impl is None  # no pynput listener created on Wayland
    assert captured and "portal" in captured[0].lower()
    assert "Wayland" in hl.last_status or "portal" in hl.last_status.lower()


def test_none_backend_emits_unavailable(monkeypatch):
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.NONE)
    hl = hk.HotkeyListener()
    captured = []
    hl.backend_unavailable.connect(lambda m: captured.append(m))
    hl.start()
    assert captured and "backend" in captured[0].lower()


class _FakeImpl:
    def __init__(self, listener, trusted):
        self._listener = listener
        self.is_running = False
        self._trusted = trusted
        self.started = False

    @property
    def is_trusted(self):
        return self._trusted

    def start(self):
        self.started = True
        self.is_running = True

    def stop(self):
        self.is_running = False

    def update_config(self, *_):
        pass


def test_macos_untrusted_surfaces_accessibility_guidance(monkeypatch):
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.PYNPUT)
    monkeypatch.setattr(caps, "is_macos", lambda: True)
    hl = hk.HotkeyListener()
    # Inject a fake impl that reports NOT trusted (permission denied).
    monkeypatch.setattr(hk, "_PynputHotkeyListenerImpl", lambda listener: _FakeImpl(listener, trusted=False))
    captured = []
    hl.backend_unavailable.connect(lambda m: captured.append(m))
    hl.start()
    assert hl.accessibility_trusted() is False
    assert captured and "Accessibility" in captured[0]


def test_macos_trusted_sets_active_status(monkeypatch):
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.PYNPUT)
    hl = hk.HotkeyListener()
    monkeypatch.setattr(hk, "_PynputHotkeyListenerImpl", lambda listener: _FakeImpl(listener, trusted=True))
    hl.start()
    assert hl.accessibility_trusted() is True
    assert "active" in hl.last_status.lower()


def test_single_state_machine_press_release(monkeypatch):
    """The listener must not emit duplicate press events (single state machine
    preserved) — _on_hotkey_pressed is idempotent while active."""
    _app()
    monkeypatch.setattr(caps, "hotkey_backend", lambda: caps.HotkeyBackend.PYNPUT)
    hl = hk.HotkeyListener()
    presses, releases = [], []
    hl.hotkey_pressed.connect(lambda: presses.append(1))
    hl.hotkey_released.connect(lambda: releases.append(1))
    hl._on_hotkey_pressed()
    hl._on_hotkey_pressed()  # repeat while active -> ignored
    hl._on_hotkey_released()
    hl._on_hotkey_released()  # repeat while inactive -> ignored
    assert presses == [1]
    assert releases == [1]
