"""ReminderScheduler (QTimer) lifecycle + full end-to-end scenario tests.

Uses a real QApplication but drives time via an injected clock and a
FakeNotifier, so nothing depends on wall-clock timing. The QTimer is started and
stopped to prove clean lifecycle and single-instance behavior.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from sayit.core.conversation import ConversationEngine  # noqa: E402
from sayit.core.reminders import (  # noqa: E402
    FakeNotifier,
    ReminderScheduler,
    ReminderService,
    ReminderStatus,
    ReminderStore,
)

ET = ZoneInfo("America/New_York")


def _app():
    return QApplication.instance() or QApplication([])


def test_scheduler_start_stop_single_timer(tmp_path):
    _app()
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    store = ReminderStore(path=tmp_path / "r.json", clock=lambda: now)
    sched = ReminderScheduler(store, FakeNotifier(), local_tz=ET, interval_ms=100000)
    sched.start()
    assert sched.is_running is True
    # A second start() must not create a competing timer.
    first_timer = sched._timer
    sched.start()
    assert sched._timer is first_timer
    sched.stop()
    assert sched.is_running is False
    assert sched._timer is None
    # stop() is idempotent.
    sched.stop()


def test_scheduler_start_reconciles_missed(tmp_path):
    _app()
    from sayit.core.reminders import Reminder, build_trigger

    create_now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    store = ReminderStore(path=tmp_path / "r.json", clock=lambda: create_now)
    store.add(Reminder(title="Missed",
                       trigger_at=build_trigger("2026-10-20", "10:00", tz=ET, now=create_now)))
    later = _dt.datetime(2026, 10, 20, 12, 0, tzinfo=ET)
    store2 = ReminderStore(path=tmp_path / "r.json", clock=lambda: later)
    fake = FakeNotifier()
    sched = ReminderScheduler(store2, fake, local_tz=ET, interval_ms=100000)
    fired = sched.start()
    assert len(fired) == 1 and fired[0].missed is True
    sched.stop()


# --- FULL END-TO-END: create -> confirm -> persist -> restart -> notify -----
#     -> reschedule -> cancel ------------------------------------------------
def test_end_to_end_reminder_lifecycle(tmp_path):
    _app()
    p = tmp_path / "reminders.json"

    # (1) CREATE via conversation at 09:00 ET on 2026-10-20.
    now1 = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    store1 = ReminderStore(path=p, clock=lambda: now1)
    svc1 = ReminderService(store1, local_tz=ET)
    eng = ConversationEngine(today=now1.date())
    eng.handle_turn("Remind me about the project meeting tomorrow at 10 AM.")
    task = eng.state.active_task()

    # (2) CONFIRM + (3) PERSIST.
    svc1.request_confirmation(task)
    res = svc1.confirm_and_schedule(task, expected_revision=task.revision_number)
    assert res.ok and store1.count() == 1
    rid = res.reminder.id

    # (4) RESTART: a fresh store reads the persisted reminder; it is still
    #     pending and in the future (tomorrow 10:00), so nothing fires yet.
    store2 = ReminderStore(path=p, clock=lambda: now1)
    fake = FakeNotifier()
    sched = ReminderScheduler(store2, fake, local_tz=ET, interval_ms=100000)
    assert store2.count() == 1
    assert sched.start() == []  # not due yet
    assert fake.calls == []
    sched.stop()

    # (5) NOTIFY: "time passes" — restart after the trigger. Reconcile fires it.
    now2 = _dt.datetime(2026, 10, 21, 10, 0, tzinfo=ET)
    store3 = ReminderStore(path=p, clock=lambda: now2)
    fake2 = FakeNotifier()
    sched2 = ReminderScheduler(store3, fake2, local_tz=ET, interval_ms=100000)
    fired = sched2.start()
    assert len(fired) == 1 and fake2.calls
    assert store3.get(rid).status is ReminderStatus.NOTIFIED
    sched2.stop()

    # (6) RESCHEDULE the (now fired) reminder to a new future time via the
    #     service: it re-activates and the scheduler watches it again.
    svc3 = ReminderService(store3, local_tz=ET)
    rr = svc3.reschedule(rid, date_iso="2026-10-22", time_24h="14:00",
                         source_text="move to Thursday 2pm")
    assert rr.ok
    assert store3.get(rid).status is ReminderStatus.PENDING
    assert store3.get(rid).trigger_at.astimezone(ET).day == 22

    # (7) CANCEL.
    cc = svc3.cancel(rid, source_text="cancel that")
    assert cc.ok
    assert store3.get(rid).status is ReminderStatus.CANCELLED

    # Final restart proves the cancellation persisted and nothing fires.
    store4 = ReminderStore(path=p, clock=lambda: _dt.datetime(2026, 10, 23, 9, 0, tzinfo=ET))
    fake3 = FakeNotifier()
    sched3 = ReminderScheduler(store4, fake3, local_tz=ET, interval_ms=100000)
    assert sched3.start() == []  # cancelled -> never fires
    assert fake3.calls == []
    sched3.stop()
