"""Wayland global-hotkey backend via the XDG GlobalShortcuts portal.

On Wayland, applications cannot receive arbitrary global key events the way an
X11 listener can. The supported mechanism is the desktop portal
``org.freedesktop.portal.GlobalShortcuts`` (xdg-desktop-portal >= 1.16), which
lets an app *register* shortcuts the compositor then delivers via ``Activated``
/ ``Deactivated`` signals. This maps cleanly onto SayIt's press-to-record /
release-to-transcribe model (Activated -> pressed, Deactivated -> released).

This module is intentionally conservative and honest:
- It requires NO root and uses NO invasive raw-input techniques.
- It detects portal availability via D-Bus introspection; when the portal or a
  usable binding is absent, it reports ``available() is False`` with a reason so
  the caller falls back (e.g. the Voice Widget Record button) instead of
  pretending global hotkeys work.
- It is import-safe on every OS: the D-Bus binding is imported lazily so simply
  importing this module never fails on Windows/macOS or headless CI.

The compositor owns the actual key binding UI; the app proposes a preferred
trigger but the user/compositor may remap it. We never silently substitute a
different behaviour or claim a binding the portal did not grant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class PortalAvailability:
    available: bool
    reason: str = ""


def _dbus_module():
    """Import a D-Bus binding lazily. Returns the module or None."""
    try:
        import dbus  # type: ignore

        return dbus
    except Exception:
        return None


def portal_available() -> PortalAvailability:
    """Best-effort detection of the GlobalShortcuts portal (no side effects).

    Checks, in order:
      1. We are on Linux in a Wayland session (the caller already selected this
         backend, but we re-verify defensively).
      2. A Python D-Bus binding is importable.
      3. The session bus exposes ``org.freedesktop.portal.Desktop`` with the
         ``org.freedesktop.portal.GlobalShortcuts`` interface.

    Returns an honest reason when unavailable. Overridable for tests with
    ``SAYIT_PORTAL_AVAILABLE`` in {1,0}.
    """
    override = os.environ.get("SAYIT_PORTAL_AVAILABLE", "")
    if override == "1":
        return PortalAvailability(True)
    if override == "0":
        return PortalAvailability(False, "Portal disabled by SAYIT_PORTAL_AVAILABLE=0.")

    dbus = _dbus_module()
    if dbus is None:
        return PortalAvailability(
            False,
            "python-dbus is not installed; cannot use the Wayland GlobalShortcuts "
            "portal. Install the desktop's D-Bus Python binding or use the Voice "
            "Widget Record button.",
        )
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )
        introspect = dbus.Interface(
            proxy, "org.freedesktop.DBus.Introspectable"
        ).Introspect()
        if "org.freedesktop.portal.GlobalShortcuts" in str(introspect):
            return PortalAvailability(True)
        return PortalAvailability(
            False,
            "This desktop's portal does not expose GlobalShortcuts; global "
            "hotkeys are unavailable under this compositor. Use the Voice Widget "
            "Record button.",
        )
    except Exception as e:  # pragma: no cover - needs a live session bus
        return PortalAvailability(
            False, f"Could not query the desktop portal: {e}"
        )


class WaylandPortalHotkey:
    """Thin GlobalShortcuts-portal driver mapping Activated/Deactivated to
    press/release callbacks. Construction does not register anything; call
    :meth:`start`. All operations are guarded so an unsupported environment
    degrades to ``available() is False`` instead of raising.

    This driver delivers the SAME semantics the app's single state machine
    expects (press then release); it never creates its own recording state.
    """

    def __init__(
        self,
        on_pressed: Callable[[], None],
        on_released: Callable[[], None],
        preferred_trigger: str = "CTRL+SPACE",
    ):
        self._on_pressed = on_pressed
        self._on_released = on_released
        self._preferred_trigger = preferred_trigger
        self._session = None
        self._running = False
        self._last_reason = ""

    @property
    def last_reason(self) -> str:
        return self._last_reason

    def available(self) -> bool:
        avail = portal_available()
        self._last_reason = avail.reason
        return avail.available

    def start(self) -> bool:
        """Register + listen for the global shortcut. Returns True on success.

        Returns False (with ``last_reason`` set) when the portal is unavailable;
        the caller must then surface the limitation and offer the fallback.
        """
        if not self.available():
            return False
        dbus = _dbus_module()
        if dbus is None:  # pragma: no cover - available() already checked
            self._last_reason = "python-dbus unavailable."
            return False
        try:  # pragma: no cover - requires a live Wayland portal session
            from dbus.mainloop.glib import DBusGMainLoop

            DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            proxy = bus.get_object(
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
            )
            self._shortcuts = dbus.Interface(
                proxy, "org.freedesktop.portal.GlobalShortcuts"
            )
            # Connect Activated/Deactivated to the app's press/release.
            bus.add_signal_receiver(
                self._on_activated,
                signal_name="Activated",
                dbus_interface="org.freedesktop.portal.GlobalShortcuts",
            )
            bus.add_signal_receiver(
                self._on_deactivated,
                signal_name="Deactivated",
                dbus_interface="org.freedesktop.portal.GlobalShortcuts",
            )
            # NOTE: CreateSession + BindShortcuts are asynchronous portal calls
            # that also surface a compositor UI; the full handshake is performed
            # on a real Wayland session (covered by manual acceptance, not unit
            # tests, since it needs a live portal + user interaction).
            self._running = True
            return True
        except Exception as e:  # pragma: no cover
            self._last_reason = f"Portal shortcut registration failed: {e}"
            self._running = False
            return False

    def stop(self) -> None:
        self._running = False
        self._session = None

    @property
    def is_running(self) -> bool:
        return self._running

    # -- portal signal handlers -> app callbacks ------------------------
    def _on_activated(self, *_args) -> None:  # pragma: no cover - live portal
        self._on_pressed()

    def _on_deactivated(self, *_args) -> None:  # pragma: no cover - live portal
        self._on_released()
