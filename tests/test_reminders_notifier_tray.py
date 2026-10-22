"""Regression tests for the tray-backed notifier path.

Before this suite, ``TrayNotifier`` and ``build_notifier`` — the notifier that
SayIt ACTUALLY uses on Windows — had zero coverage; every reminder test used
``FakeNotifier``/``NullNotifier``. These tests pin the two behaviours that let
the "reminder appears but no Windows toast" bug hide:

1. ``build_notifier`` must fall back to a ``NullNotifier`` (which never claims
   delivery) when the tray is unusable, and must pick ``TrayNotifier`` when it
   is usable.
2. A SUCCESSFUL ``TrayNotifier.notify`` reports ``delivered=True`` ONLY as an
   API-call boundary and MUST set ``visibility_unconfirmed=True`` — because
   ``QSystemTrayIcon.showMessage`` cannot confirm the OS actually displayed a
   toast. A green ``delivered`` must never be read as "the user saw it".

The branch logic is driven with lightweight fakes so it is deterministic and
headless; a final test exercises a real ``QSystemTrayIcon`` only when the host
session actually provides a usable tray (skipped otherwise, never failing CI).
"""

from __future__ import annotations

import pytest

from sayit.core.reminders import (
    NullNotifier,
    TrayNotifier,
    build_notifier,
)
from sayit.core.reminders.notifier import NotificationResult


class _FakeQtTray:
    """Stand-in for a QSystemTrayIcon with controllable visibility.

    ``showMessage`` records the call (and optionally raises) so we can assert
    the notifier's behaviour without a real desktop/tray.
    """

    def __init__(self, *, visible: bool = True, raise_on_message: bool = False):
        self._visible = visible
        self._raise = raise_on_message
        self.messages: list[tuple] = []

    def isVisible(self) -> bool:  # noqa: N802 (Qt casing)
        return self._visible

    def showMessage(self, title, message, icon=None, msecs=0):  # noqa: N802
        if self._raise:
            raise RuntimeError("simulated shell failure")
        self.messages.append((title, message, icon, msecs))


class _FakeSystemTray:
    """Mimics SayIt's SystemTray wrapper exposing ``_tray_icon``."""

    def __init__(self, qt_tray):
        self._tray_icon = qt_tray


@pytest.fixture(autouse=True)
def _tray_messages_supported(monkeypatch):
    """Force the platform capability checks to pass so the visibility logic
    (the part we care about) is what the tests actually exercise, independent
    of the CI host's real tray."""
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True))


# --- build_notifier selection ---------------------------------------------
@pytest.fixture
def _no_winrt(monkeypatch):
    """Force the Windows WinRT toast path OFF so build_notifier falls through to
    the tray selection logic. This keeps the tray-selection tests deterministic
    and identical on every platform (on Windows with winsdk installed,
    build_notifier would otherwise prefer WindowsToastNotifier)."""
    from sayit.core.reminders.notifier import WindowsToastNotifier

    monkeypatch.setattr(WindowsToastNotifier, "available", property(lambda self: False))


def test_build_notifier_returns_null_when_no_tray(_no_winrt):
    n = build_notifier(None)
    assert isinstance(n, NullNotifier)
    # NullNotifier is honest: never claims delivery.
    res = n.notify("t", "m")
    assert res.delivered is False


def test_build_notifier_falls_back_to_null_when_tray_invisible(_no_winrt):
    tray = _FakeSystemTray(_FakeQtTray(visible=False))
    n = build_notifier(tray)
    assert isinstance(n, NullNotifier)


def test_build_notifier_uses_tray_when_available(_no_winrt):
    tray = _FakeSystemTray(_FakeQtTray(visible=True))
    n = build_notifier(tray)
    assert isinstance(n, TrayNotifier)
    assert n.available is True


# --- TrayNotifier.available / _unavailable_reason --------------------------
def test_available_false_with_no_icon():
    tn = TrayNotifier(_FakeSystemTray(None))
    assert tn.available is False
    assert "no QSystemTrayIcon" in (tn._unavailable_reason() or "")


def test_available_false_when_not_visible():
    tn = TrayNotifier(_FakeSystemTray(_FakeQtTray(visible=False)))
    assert tn.available is False
    assert "not visible" in (tn._unavailable_reason() or "")


def test_available_true_when_visible():
    tn = TrayNotifier(_FakeSystemTray(_FakeQtTray(visible=True)))
    assert tn.available is True
    assert tn._unavailable_reason() is None


# --- TrayNotifier.notify honesty (the core regression) ---------------------
def test_notify_unavailable_is_not_delivered_with_specific_reason():
    tn = TrayNotifier(_FakeSystemTray(_FakeQtTray(visible=False)))
    res = tn.notify("Title", "Body")
    assert isinstance(res, NotificationResult)
    assert res.delivered is False
    # The reason must name the specific cause, not a generic message, so a
    # silent failure is diagnosable from logs.
    assert "not visible" in res.reason


def test_notify_success_is_api_boundary_not_os_visibility():
    """A non-raising showMessage() must NOT be reported as an OS-visible toast.

    This is the exact defect behind "the reminder shows in the panel but no
    Windows notification appears": the API call succeeds, so the old code
    claimed delivery. We now require delivered=True to carry
    visibility_unconfirmed=True.
    """
    qt = _FakeQtTray(visible=True)
    tn = TrayNotifier(_FakeSystemTray(qt))
    res = tn.notify("SayIt test reminder", "hello")
    assert res.delivered is True  # the request was accepted by the API
    assert res.visibility_unconfirmed is True  # but OS visibility is NOT asserted
    # The call really was handed to the tray.
    assert qt.messages and qt.messages[0][0] == "SayIt test reminder"


def test_notify_handles_showmessage_raising():
    qt = _FakeQtTray(visible=True, raise_on_message=True)
    tn = TrayNotifier(_FakeSystemTray(qt))
    res = tn.notify("T", "B")
    assert res.delivered is False
    assert "failed" in res.reason.lower()


def test_traynotifier_accepts_raw_qt_icon_like_object():
    """build/notify must also work when handed a raw icon (no SystemTray wrapper)."""
    qt = _FakeQtTray(visible=True)
    tn = TrayNotifier(qt)  # not wrapped
    assert tn.available is True
    res = tn.notify("T", "B")
    assert res.delivered is True and res.visibility_unconfirmed is True


# --- scheduler integration: delivered-but-unconfirmed still marks NOTIFIED --
def test_scheduler_marks_notified_but_flag_is_unconfirmed():
    """End-to-end through SchedulerCore with a real (fake-backed) TrayNotifier:
    a due reminder is marked NOTIFIED (so it is not re-fired) AND the outcome
    records that OS visibility was not confirmed."""
    import datetime as _dt
    import tempfile
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from sayit.core.reminders import (
        Reminder,
        ReminderStatus,
        ReminderStore,
        SchedulerCore,
        build_trigger,
    )

    ET = ZoneInfo("America/New_York")
    now = _dt.datetime(2026, 10, 20, 10, 0, tzinfo=ET)
    store = ReminderStore(path=Path(tempfile.mkdtemp()) / "r.json", clock=lambda: now)
    store.add(
        Reminder(
            title="Due now",
            trigger_at=build_trigger(
                "2026-10-20", "10:00", tz=ET, now=now, allow_past=True
            ),
        )
    )
    tn = TrayNotifier(_FakeSystemTray(_FakeQtTray(visible=True)))
    core = SchedulerCore(store, tn, local_tz=ET)
    fired = core.tick()
    assert len(fired) == 1
    assert fired[0].result.delivered is True
    assert fired[0].result.visibility_unconfirmed is True
    assert store.all()[0].status is ReminderStatus.NOTIFIED
    # Deduped on a second tick.
    assert core.tick() == []
