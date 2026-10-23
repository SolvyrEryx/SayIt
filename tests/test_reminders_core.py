"""Deterministic reminder model/store/scheduler/notifier tests.

All time is injected (fixed clock); notifications use a FakeNotifier. No real
sleeping, no Qt timers, no network. Timezone via zoneinfo.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sayit.core.reminders import (
    FakeNotifier,
    NullNotifier,
    Reminder,
    ReminderError,
    ReminderStatus,
    ReminderStore,
    SchedulerCore,
    build_trigger,
)

ET = ZoneInfo("America/New_York")


def _clock(dtv: _dt.datetime):
    return lambda: dtv


# --- model: validation + timezone ------------------------------------------
def test_reminder_requires_aware_trigger():
    with pytest.raises(ReminderError):
        Reminder(title="x", trigger_at=_dt.datetime(2026, 10, 21, 10, 0))  # naive


def test_reminder_requires_title():
    with pytest.raises(ReminderError):
        Reminder(title="  ", trigger_at=_dt.datetime(2026, 10, 21, 10, 0, tzinfo=ET))


def test_build_trigger_resolves_date_time_in_tz():
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    trig = build_trigger("2026-10-21", "10:00", tz=ET, now=now)
    assert trig.tzinfo is not None
    assert trig.hour == 10 and trig.date().isoformat() == "2026-10-21"


def test_build_trigger_rejects_past():
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    with pytest.raises(ReminderError):
        build_trigger("2026-10-19", "10:00", tz=ET, now=now)


def test_build_trigger_allow_past_for_reconcile():
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    trig = build_trigger("2026-10-19", "10:00", tz=ET, now=now, allow_past=True)
    assert trig.date().isoformat() == "2026-10-19"


def test_build_trigger_default_time():
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    trig = build_trigger("2026-10-21", None, tz=ET, now=now, default_time="08:30")
    assert trig.hour == 8 and trig.minute == 30


# --- DST: America/New_York 'fall back' is 2026-11-01 ------------------------
def test_dst_trigger_offsets_differ_across_transition():
    # Before DST ends (EDT, -04:00) vs after (EST, -05:00).
    before = build_trigger("2026-10-30", "10:00", tz=ET,
                           now=_dt.datetime(2026, 10, 1, 9, 0, tzinfo=ET))
    after = build_trigger("2026-11-05", "10:00", tz=ET,
                          now=_dt.datetime(2026, 10, 1, 9, 0, tzinfo=ET))
    assert before.utcoffset() != after.utcoffset()
    # Both are stored unambiguously (round-trip through ISO preserves offset).
    assert Reminder.from_dict(
        Reminder(title="x", trigger_at=after).to_dict()
    ).trigger_utc() == after.astimezone(_dt.timezone.utc)


# --- store: persistence + restart ------------------------------------------
def test_store_add_persists_and_restores(tmp_path):
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    p = tmp_path / "reminders.json"
    store = ReminderStore(path=p, clock=_clock(now))
    r = Reminder(title="Meeting", trigger_at=build_trigger("2026-10-21", "10:00", tz=ET, now=now))
    store.add(r)
    assert p.exists()
    store2 = ReminderStore(path=p, clock=_clock(now))
    assert store2.count() == 1
    assert store2.all()[0].title == "Meeting"


def test_store_idempotent_add(tmp_path):
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    store = ReminderStore(path=tmp_path / "r.json", clock=_clock(now))
    trig = build_trigger("2026-10-21", "10:00", tz=ET, now=now)
    r1 = Reminder(title="A", trigger_at=trig, idempotency_key="prop-1")
    store.add(r1)
    r2 = Reminder(title="A dup", trigger_at=trig, idempotency_key="prop-1")
    returned = store.add(r2)
    assert store.count() == 1
    assert returned.id == r1.id  # existing returned, no duplicate


def test_store_corrupt_file_recovers(tmp_path):
    p = tmp_path / "reminders.json"
    p.write_text("{ not valid json ]", encoding="utf-8")
    store = ReminderStore(path=p, clock=_clock(_dt.datetime.now(_dt.timezone.utc)))
    assert store.count() == 0
    assert (tmp_path / "reminders.corrupt.bak").exists()


def test_store_skips_single_malformed_reminder(tmp_path):
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    good = Reminder(title="Good", trigger_at=build_trigger("2026-10-21", "10:00", tz=ET, now=now))
    payload = {"schema_version": 1, "reminders": [good.to_dict(), {"title": "bad", "trigger_at": "not-a-date"}]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    store = ReminderStore(path=p, clock=_clock(now))
    assert store.count() == 1  # the good one survives


# --- scheduler: due delivery + dedupe --------------------------------------
def test_tick_fires_due_reminder_once():
    now = _dt.datetime(2026, 10, 20, 10, 0, tzinfo=ET)
    import tempfile
    store = ReminderStore(path=Path(tempfile.mkdtemp()) / "r.json", clock=_clock(now))
    store.add(Reminder(title="Now", trigger_at=build_trigger("2026-10-20", "10:00", tz=ET, now=now, allow_past=True)))
    fake = FakeNotifier()
    core = SchedulerCore(store, fake, local_tz=ET)
    fired = core.tick()
    assert len(fired) == 1 and fake.calls
    assert store.all()[0].status is ReminderStatus.NOTIFIED
    # Dedupe: a second tick does not re-fire.
    assert core.tick() == []


def test_future_reminder_not_fired():
    now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    import tempfile
    store = ReminderStore(path=Path(tempfile.mkdtemp()) / "r.json", clock=_clock(now))
    store.add(Reminder(title="Later", trigger_at=build_trigger("2026-10-20", "17:00", tz=ET, now=now)))
    core = SchedulerCore(store, FakeNotifier(), local_tz=ET)
    assert core.tick() == []


# --- scheduler: missed reminders after restart -----------------------------
def test_reconcile_fires_overdue_missed_once():
    # Scheduled for the past; app "starts" after the trigger passed.
    create_now = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)
    import tempfile
    p = Path(tempfile.mkdtemp()) / "r.json"
    store = ReminderStore(path=p, clock=_clock(create_now))
    store.add(Reminder(title="Missed", trigger_at=build_trigger("2026-10-20", "10:00", tz=ET, now=create_now)))
    # Restart later, trigger already passed.
    later = _dt.datetime(2026, 10, 20, 12, 0, tzinfo=ET)
    store2 = ReminderStore(path=p, clock=_clock(later))
    fake = FakeNotifier()
    core = SchedulerCore(store2, fake, local_tz=ET)
    out = core.reconcile()
    assert len(out) == 1 and out[0].missed is True
    assert "(missed)" in fake.calls[0][1]
    # Never fires again.
    assert core.tick() == []


# --- notifier honesty ------------------------------------------------------
def test_unavailable_notifier_does_not_mark_notified():
    now = _dt.datetime(2026, 10, 20, 10, 0, tzinfo=ET)
    import tempfile
    store = ReminderStore(path=Path(tempfile.mkdtemp()) / "r.json", clock=_clock(now))
    store.add(Reminder(title="X", trigger_at=build_trigger("2026-10-20", "10:00", tz=ET, now=now, allow_past=True)))
    core = SchedulerCore(store, NullNotifier(), local_tz=ET)
    fired = core.tick()
    # Attempt recorded as not delivered; reminder stays PENDING (not consumed).
    assert fired and fired[0].result.delivered is False
    assert store.all()[0].status is ReminderStatus.PENDING


def test_failing_notifier_not_reported_delivered():
    now = _dt.datetime(2026, 10, 20, 10, 0, tzinfo=ET)
    import tempfile
    store = ReminderStore(path=Path(tempfile.mkdtemp()) / "r.json", clock=_clock(now))
    store.add(Reminder(title="X", trigger_at=build_trigger("2026-10-20", "10:00", tz=ET, now=now, allow_past=True)))
    fake = FakeNotifier(fail=True)
    core = SchedulerCore(store, fake, local_tz=ET)
    fired = core.tick()
    assert fired[0].result.delivered is False
    assert fake.calls == []  # a failed delivery recorded no "shown" call
    assert store.all()[0].status is ReminderStatus.PENDING  # retried next tick
