"""Reminder scheduler: fires due reminders while SayIt is running.

Two layers:
* A PURE core (``reconcile`` + ``tick``) that is fully deterministic with an
  injected clock and a fake notifier — no Qt, no real time — so every policy
  (missed-reminder handling, dedupe, DST) is unit-testable.
* A thin ``ReminderScheduler`` that owns ONE ``QTimer`` on the GUI thread which
  periodically calls ``tick``. The timer does no blocking work; firing a
  notification is a fast, local call. There are no background threads and only
  one timer instance, so there are never competing schedulers.

MISSED-REMINDER POLICY (documented + enforced):
  On startup / reconciliation, every ACTIVE reminder whose trigger is already
  in the past is fired ONCE immediately (a single "catch-up" notification that
  states it was missed), then marked NOTIFIED. We never replay a burst of old
  notifications and never fire the same reminder twice (status gates it).

RUNTIME LIMITATION (disclosed in the UI): reminders only fire while SayIt is
running. SayIt does not install an OS background service, so a reminder whose
time passes while SayIt is closed fires at the next launch (catch-up), not at
the exact moment.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Callable, List, Optional

from ...utils.logger import get_logger
from .model import Reminder, ReminderStatus
from .notifier import Notifier, NotificationResult

logger = get_logger(__name__)


@dataclass
class FireOutcome:
    reminder_id: str
    title: str
    missed: bool
    result: NotificationResult


def _format_message(reminder: Reminder, *, missed: bool, tz: _dt.tzinfo) -> str:
    local = reminder.trigger_at.astimezone(tz)
    when = local.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
    if missed:
        return f"(missed) was due {when}. {reminder.description}".strip()
    return f"Scheduled for {when}. {reminder.description}".strip()


class SchedulerCore:
    """Pure scheduling logic. Deterministic; no Qt, no real clock."""

    def __init__(
        self,
        store,
        notifier: Notifier,
        *,
        local_tz: Optional[_dt.tzinfo] = None,
    ):
        self._store = store
        self._notifier = notifier
        self._tz = local_tz or _dt.datetime.now().astimezone().tzinfo or _dt.timezone.utc

    def set_notifier(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def _fire(self, reminder: Reminder, *, now: _dt.datetime, missed: bool) -> FireOutcome:
        msg = _format_message(reminder, missed=missed, tz=self._tz)
        result = self._notifier.notify(reminder.title, msg)
        if result.delivered:
            # Only mark NOTIFIED when the OS actually accepted the request, so a
            # failed/unavailable notifier does not silently "consume" a reminder.
            reminder.mark_notified(when=now.timestamp())
            self._store.update(reminder)
            if result.visibility_unconfirmed:
                # Honest boundary: the request was handed to the OS but no API
                # confirms the toast was actually shown (Windows tray balloon).
                logger.info(
                    "Reminder handed to OS id=%s missed=%s (OS-visible display "
                    "NOT confirmed by the notifier API)",
                    reminder.id,
                    missed,
                )
            else:
                logger.info("Reminder fired id=%s missed=%s", reminder.id, missed)
        else:
            logger.warning(
                "Reminder NOT delivered id=%s reason=%s", reminder.id, result.reason
            )
        return FireOutcome(reminder.id, reminder.title, missed, result)

    def reconcile(self, *, now: Optional[_dt.datetime] = None) -> List[FireOutcome]:
        """Startup catch-up: fire overdue reminders once, newest policy applied.

        Called on launch. Every active, already-due reminder fires a single
        missed notification. Non-due reminders are left for ``tick``.
        """
        now = now or self._store.now()
        outcomes: List[FireOutcome] = []
        for r in self._store.active():
            if r.is_due(now):
                outcomes.append(self._fire(r, now=now, missed=True))
        return outcomes

    def tick(self, *, now: Optional[_dt.datetime] = None) -> List[FireOutcome]:
        """Fire reminders that have just become due. Dedupe via status.

        Safe to call repeatedly: a reminder already NOTIFIED is no longer active
        and will not re-fire. Returns outcomes for anything fired this tick.
        """
        now = now or self._store.now()
        outcomes: List[FireOutcome] = []
        for r in self._store.active():
            if r.is_due(now):
                outcomes.append(self._fire(r, now=now, missed=False))
        return outcomes


class ReminderScheduler:
    """QTimer-driven wrapper around SchedulerCore (GUI-thread, non-blocking)."""

    DEFAULT_INTERVAL_MS = 20_000  # check every 20s; fast, cheap, non-blocking

    def __init__(
        self,
        store,
        notifier: Notifier,
        *,
        local_tz: Optional[_dt.tzinfo] = None,
        interval_ms: Optional[int] = None,
        on_fire: Optional[Callable[[List[FireOutcome]], None]] = None,
    ):
        self.core = SchedulerCore(store, notifier, local_tz=local_tz)
        self._interval_ms = interval_ms or self.DEFAULT_INTERVAL_MS
        self._on_fire = on_fire
        self._timer = None
        self._started = False

    def start(self) -> List[FireOutcome]:
        """Reconcile overdue reminders, then start the periodic timer.

        Returns the startup catch-up outcomes (for logging/UI). Idempotent: a
        second start() does not create a second timer.
        """
        catch_up = self.core.reconcile()
        if catch_up and self._on_fire:
            self._on_fire(catch_up)
        if not self._started:
            from PySide6.QtCore import QTimer

            self._timer = QTimer()
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._on_tick)
            self._timer.start()
            self._started = True
        return catch_up

    def _on_tick(self) -> None:
        try:
            fired = self.core.tick()
            # Heartbeat: proves the QTimer is actually firing. If no reminder
            # ever appears AND this line is absent from the logs, the scheduler
            # never triggered (timer not started / event loop blocked) — which
            # is a different failure from a notifier that was called but the OS
            # did not display anything.
            logger.debug("Reminder tick ran; fired=%d", len(fired))
            if fired and self._on_fire:
                self._on_fire(fired)
        except Exception as e:  # pragma: no cover - defensive; never kill the timer
            logger.error("Reminder tick failed: %s", e)

    def stop(self) -> None:
        """Stop the timer cleanly on shutdown. Idempotent."""
        if self._timer is not None:
            try:
                self._timer.stop()
                self._timer.timeout.disconnect(self._on_tick)
            except (RuntimeError, TypeError):
                pass
            self._timer = None
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started
