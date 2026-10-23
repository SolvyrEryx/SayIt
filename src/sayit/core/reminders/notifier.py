"""Desktop notification abstraction for reminders.

Honest by design: a notifier reports whether delivery was actually ATTEMPTED
and whether the capability exists, rather than pretending a notification was
shown when the OS/tray rejected it. The scheduler only marks a reminder
``NOTIFIED`` when the notifier reports a successful attempt.

Backends:
* ``WindowsToastNotifier`` — Windows only. Raises a real WinRT
  ``ToastNotification`` under SayIt's AppUserModelID (``VptrCipher.SayIt``) via
  ``winsdk``. Unlike the legacy tray balloon, a WinRT toast is surfaced by the
  modern notification platform AND persisted to the Action Center, so the user
  can still see a missed reminder. This is the preferred Windows backend.
* ``TrayNotifier`` — uses the existing ``QSystemTrayIcon.showMessage`` (native
  balloon/notification on Windows, Notification Center on macOS, libnotify/DBus
  on Linux when the tray host supports it). Reuses SayIt's existing tray. On
  modern Windows the balloon is unreliable (it is handed to the shell but is
  frequently not rendered and does NOT persist to Action Center), which is why
  ``WindowsToastNotifier`` is preferred there; this remains the fallback and
  the primary path on macOS/Linux.
* ``FakeNotifier`` — records calls for deterministic tests (no GUI).
* ``NullNotifier`` — a no-op that honestly reports ``available=False`` when no
  notification surface exists.

Platform note: ``QSystemTrayIcon.showMessage`` cannot confirm the user actually
SAW the toast (no OS API guarantees that). We report that the request was
delivered to the OS, which is the honest, verifiable boundary. The WinRT path
additionally persists to the Action Center, a stronger (still not eyeball-level)
guarantee that the notification is user-reachable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ...utils.logger import get_logger

logger = get_logger(__name__)

# Keep in sync with WINDOWS_APP_USER_MODEL_ID in sayit/app.py and the installer
# shortcut AUMID. A WinRT toast is only delivered + attributed when this exact
# AUMID is also stamped on the launching shortcut (see installer.iss).
WINDOWS_APP_USER_MODEL_ID = "VptrCipher.SayIt"


@dataclass(frozen=True)
class NotificationResult:
    # ``delivered`` means the request was accepted by the OS/tray API WITHOUT
    # error. It is an API-call boundary, NOT a guarantee that the user saw a
    # toast: no cross-platform API confirms on-screen visibility. Do not treat
    # ``delivered=True`` as "the notification appeared".
    delivered: bool  # the request was handed to the OS/tray (API ok)
    reason: str = ""  # why not, when delivered is False
    # True only for backends that CANNOT assert OS visibility (e.g. the Windows
    # tray balloon). Lets the scheduler/UI log an honest caveat instead of
    # claiming the toast was shown.
    visibility_unconfirmed: bool = False


@runtime_checkable
class Notifier(Protocol):
    @property
    def available(self) -> bool: ...

    def notify(self, title: str, message: str) -> NotificationResult: ...


class FakeNotifier:
    """Deterministic test notifier. Records every notify() call."""

    def __init__(self, *, available: bool = True, fail: bool = False):
        self._available = available
        self._fail = fail
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, value: bool) -> None:
        self._available = value

    def set_fail(self, value: bool) -> None:
        self._fail = value

    def notify(self, title: str, message: str) -> NotificationResult:
        if not self._available:
            return NotificationResult(False, "Notifier unavailable.")
        if self._fail:
            # Simulate an OS-level rejection; must NOT be reported as delivered.
            return NotificationResult(False, "Notification backend failed.")
        self.calls.append((title, message))
        return NotificationResult(True)


class NullNotifier:
    """Honest no-op: never claims delivery."""

    @property
    def available(self) -> bool:
        return False

    def notify(self, title: str, message: str) -> NotificationResult:
        return NotificationResult(
            False, "No desktop notification surface is available."
        )


class TrayNotifier:
    """Notifier backed by an existing QSystemTrayIcon.

    Accepts the SayIt ``SystemTray`` wrapper OR a raw ``QSystemTrayIcon``. It
    checks tray availability and whether the platform supports balloon messages
    before attempting delivery, and reports an honest failure otherwise.
    """

    def __init__(self, tray):
        self._tray = tray

    def _qt_tray(self):
        # SayIt's SystemTray wraps the icon as ``_tray_icon``.
        return getattr(self._tray, "_tray_icon", self._tray)

    def _unavailable_reason(self) -> Optional[str]:
        """Return a specific reason the tray cannot notify, or None if it can.

        Mirrors ``available`` but yields a precise, loggable cause so a silent
        failure can be distinguished from a healthy path.
        """
        try:
            from PySide6.QtWidgets import QSystemTrayIcon

            qt = self._qt_tray()
            if qt is None:
                return "no QSystemTrayIcon instance"
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return "system tray not available in this session"
            if not QSystemTrayIcon.supportsMessages():
                return "platform does not support balloon messages"
            if not bool(qt.isVisible()):
                return "tray icon is not visible yet"
            return None
        except Exception as e:
            return f"tray availability check raised: {e}"

    @property
    def available(self) -> bool:
        return self._unavailable_reason() is None

    def notify(self, title: str, message: str) -> NotificationResult:
        reason = self._unavailable_reason()
        if reason is not None:
            # (b) The notifier was reached but cannot deliver — an honest,
            # NOT-delivered result. This is distinct from "never called".
            logger.warning(
                "TrayNotifier.notify unavailable (title=%r): %s", title, reason
            )
            return NotificationResult(
                False,
                f"System tray notifications are unavailable: {reason}.",
            )
        try:
            from PySide6.QtWidgets import QSystemTrayIcon

            qt = self._qt_tray()
            qt.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 10000
            )
            # (c) The request was accepted by Qt/OS WITHOUT error. showMessage()
            # returns void and never signals whether the shell actually rendered
            # a toast (it can be suppressed by Focus Assist, disabled balloon
            # tips, or a missing AppUserModelID). We report an honest
            # "handed off, visibility unconfirmed" result — never "shown".
            logger.info(
                "TrayNotifier.notify handed to OS (title=%r); OS visibility "
                "cannot be confirmed by the API",
                title,
            )
            return NotificationResult(True, visibility_unconfirmed=True)
        except Exception as e:  # pragma: no cover - platform/Qt defensive
            logger.warning(
                "TrayNotifier.notify showMessage raised (title=%r): %s", title, e
            )
            return NotificationResult(False, f"Notification delivery failed: {e}")


class WindowsToastNotifier:
    """Windows-only notifier using the WinRT ``ToastNotification`` API.

    Why this exists: ``QSystemTrayIcon.showMessage`` emits a legacy
    ``Shell_NotifyIcon`` balloon. On Windows 10/11 that balloon is handed to the
    shell but is frequently NOT rendered as a visible toast and does NOT persist
    to the Action Center. A WinRT toast raised under the app's AppUserModelID
    (which the installer now stamps on the Start Menu shortcut) is surfaced by
    the modern notification platform and persisted to the Action Center, so a
    missed reminder is still reachable.

    Honesty: ``delivered`` means the WinRT platform ACCEPTED the toast (it is
    queued/persisted for display). No OS API confirms the pixels reached the
    user's eyes, so we still flag ``visibility_unconfirmed=True`` — but this is
    a strictly stronger guarantee than the balloon path, because the toast lands
    in the Action Center where the user can find it.
    """

    def __init__(self, app_user_model_id: str = WINDOWS_APP_USER_MODEL_ID):
        self._aumid = app_user_model_id

    @staticmethod
    def _winsdk_available() -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            import importlib.util

            return importlib.util.find_spec("winsdk") is not None
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._winsdk_available()

    @staticmethod
    def _xml_escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def notify(self, title: str, message: str) -> NotificationResult:
        if not sys.platform.startswith("win"):
            return NotificationResult(False, "WindowsToastNotifier is Windows-only.")
        try:
            from winsdk.windows.data.xml.dom import XmlDocument
            from winsdk.windows.ui.notifications import (
                ToastNotification,
                ToastNotificationManager,
            )
        except Exception as e:  # pragma: no cover - import/platform defensive
            logger.warning("WindowsToastNotifier: winsdk unavailable: %s", e)
            return NotificationResult(False, f"winsdk unavailable: {e}")
        try:
            xml = (
                "<toast><visual><binding template='ToastGeneric'>"
                f"<text>{self._xml_escape(title)}</text>"
                f"<text>{self._xml_escape(message)}</text>"
                "</binding></visual></toast>"
            )
            doc = XmlDocument()
            doc.load_xml(xml)
            toast = ToastNotification(doc)
            notifier = ToastNotificationManager.create_toast_notifier(self._aumid)
            notifier.show(toast)
            # The WinRT platform accepted + persisted the toast (Action Center).
            # Still not eyeball-confirmed, so keep the honest caveat.
            logger.info(
                "WindowsToastNotifier.notify delivered to WinRT platform "
                "(title=%r, aumid=%s); persisted to Action Center. On-screen "
                "visibility still cannot be API-confirmed.",
                title,
                self._aumid,
            )
            return NotificationResult(True, visibility_unconfirmed=True)
        except Exception as e:  # pragma: no cover - platform/WinRT defensive
            logger.warning(
                "WindowsToastNotifier.notify raised (title=%r): %s", title, e
            )
            return NotificationResult(False, f"WinRT toast delivery failed: {e}")


def build_notifier(tray=None) -> Notifier:
    """Choose the best available notifier honestly.

    Preference order:
    1. On Windows, a ``WindowsToastNotifier`` when ``winsdk`` is importable —
       the only path that reliably shows a toast AND persists to the Action
       Center under SayIt's AppUserModelID.
    2. A tray-backed ``TrayNotifier`` when a usable tray exists (the macOS/Linux
       primary path, and the Windows fallback if WinRT is unavailable).
    3. A ``NullNotifier`` that never claims delivery, so reminders are never
       silently dropped — the caller surfaces ``available`` to the user.
    """
    if sys.platform.startswith("win"):
        wt = WindowsToastNotifier()
        if wt.available:
            logger.info(
                "build_notifier: using WindowsToastNotifier (WinRT toast, "
                "persists to Action Center)"
            )
            return wt
        logger.warning(
            "build_notifier: winsdk unavailable; falling back to the tray "
            "balloon, which modern Windows may not display reliably"
        )

    if tray is not None:
        tn = TrayNotifier(tray)
        reason = tn._unavailable_reason()
        if reason is None:
            logger.info("build_notifier: using TrayNotifier (tray available)")
            return tn
        logger.warning(
            "build_notifier: tray present but unusable (%s); falling back to "
            "NullNotifier — reminders will NOT show a desktop notification",
            reason,
        )
    else:
        logger.warning(
            "build_notifier: no tray provided; using NullNotifier — reminders "
            "will NOT show a desktop notification"
        )
    return NullNotifier()
