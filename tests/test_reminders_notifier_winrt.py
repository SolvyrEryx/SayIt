"""Tests for the WinRT ``WindowsToastNotifier`` reminder backend.

Context: the reminder "fires but no visible Windows notification" bug had TWO
layers. (1) The installer shortcut lacked an AppUserModelID (fixed separately).
(2) Even with the AUMID, ``QSystemTrayIcon.showMessage`` only raises a legacy
``Shell_NotifyIcon`` balloon, which modern Windows does not reliably display and
does NOT persist to the Action Center. The fix is a WinRT ``ToastNotification``
raised under the AUMID, which both shows and persists.

These tests pin the backend's behaviour deterministically (no real WinRT call):

* ``build_notifier`` prefers ``WindowsToastNotifier`` on Windows when the WinRT
  binding is importable, and falls back to the tray otherwise.
* The notifier reports an honest NOT-delivered result off Windows / when the
  binding is missing, and never raises.
* Toast text is XML-escaped so a title/body with ``&`` or ``<`` cannot break the
  toast payload.
* A successful delivery is an API/platform-acceptance boundary that still flags
  ``visibility_unconfirmed=True`` (no API confirms the user's eyes saw it).
"""

from __future__ import annotations

import sys

import pytest

from sayit.core.reminders import (
    TrayNotifier,
    WindowsToastNotifier,
    build_notifier,
)
from sayit.core.reminders.notifier import (
    WINDOWS_APP_USER_MODEL_ID,
    NotificationResult,
)


def test_aumid_constant_matches_app_and_installer():
    # The toast is only attributed/delivered when this AUMID matches the process
    # (app.py) and the installer shortcut. Guard against a one-sided rename.
    assert WINDOWS_APP_USER_MODEL_ID == "VptrCipher.SayIt"


def test_xml_escape_neutralizes_markup():
    esc = WindowsToastNotifier._xml_escape
    assert esc('A & B <c> "d"') == "A &amp; B &lt;c&gt; &quot;d&quot;"


def test_notify_is_windows_only():
    """Off Windows the notifier must honestly report NOT delivered, never raise."""
    n = WindowsToastNotifier()
    if sys.platform.startswith("win"):
        pytest.skip("Windows path is exercised by the delivery test below")
    res = n.notify("t", "m")
    assert isinstance(res, NotificationResult)
    assert res.delivered is False
    assert "Windows-only" in res.reason


def test_notify_reports_failure_when_winsdk_import_fails(monkeypatch):
    """If winsdk cannot be imported at notify() time, report an honest failure."""
    monkeypatch.setattr(sys, "platform", "win32")
    # Make the winsdk import inside notify() fail deterministically.
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("winsdk"):
            raise ImportError("winsdk missing (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    res = WindowsToastNotifier().notify("t", "m")
    assert res.delivered is False
    assert "winsdk" in res.reason.lower()


def test_build_notifier_prefers_winrt_on_windows(monkeypatch):
    """On Windows with winsdk available, build_notifier must pick the WinRT
    toast backend over the tray balloon."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(WindowsToastNotifier, "available", property(lambda self: True))
    n = build_notifier(tray=object())  # tray present but should be bypassed
    assert isinstance(n, WindowsToastNotifier)


def test_build_notifier_falls_back_when_winrt_unavailable(monkeypatch):
    """On Windows WITHOUT winsdk, build_notifier falls back to the tray path."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(WindowsToastNotifier, "available", property(lambda self: False))

    class _QtTray:
        def isVisible(self):  # noqa: N802
            return True

        def showMessage(self, *a, **k):  # noqa: N802
            pass

    class _Wrap:
        def __init__(self, q):
            self._tray_icon = q

    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True))
    n = build_notifier(tray=_Wrap(_QtTray()))
    assert isinstance(n, TrayNotifier)


@pytest.mark.skipif(
    not sys.platform.startswith("win"), reason="WinRT delivery is Windows-only"
)
def test_windows_delivery_is_accepted_but_visibility_unconfirmed():
    """On a real Windows host with winsdk installed, a notify() call is accepted
    by the WinRT platform and flagged visibility_unconfirmed.

    Skips cleanly if winsdk is not importable in this environment (e.g. a lean
    CI image), so it never fails spuriously.
    """
    n = WindowsToastNotifier()
    if not n.available:
        pytest.skip("winsdk not importable in this environment")
    res = n.notify("SayIt test (pytest)", "winrt backend unit delivery")
    assert res.delivered is True
    assert res.visibility_unconfirmed is True
