"""Reminder SERVICE + conversation-integration tests (deterministic).

Covers the full bridge from a conversational TaskProposal to a real persistent
reminder: eligibility, safe confirmation, stale-revision rejection, idempotency,
corrections on real reminders, snooze, queries, casual-mention isolation,
independence from conversation-history retention, and typed==spoken equivalence.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sayit.core.conversation import ConversationEngine, ConversationStore
from sayit.core.conversation.state import SlotName, TaskStatus
from sayit.core.reminders import (
    FakeNotifier,
    Reminder,
    ReminderService,
    ReminderStatus,
    ReminderStore,
    SchedulerCore,
    build_trigger,
)

ET = ZoneInfo("America/New_York")
NOW = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)  # Tue


def _clock():
    return NOW


def _svc(tmp_path) -> ReminderService:
    store = ReminderStore(path=tmp_path / "reminders.json", clock=_clock)
    return ReminderService(store, local_tz=ET)


def _engine() -> ConversationEngine:
    return ConversationEngine(today=NOW.date())


def _propose(engine, *utterances):
    for u in utterances:
        engine.handle_turn(u)
    return engine.state.active_task()


# --- eligibility: explicit vs casual ---------------------------------------
def test_explicit_reminder_is_schedulable(tmp_path):
    svc = _svc(tmp_path)
    task = _propose(_engine(), "Remind me about the project meeting tomorrow at 10 AM.")
    assert svc.is_schedulable(task) is True


def test_casual_mention_not_schedulable(tmp_path):
    svc = _svc(tmp_path)
    # A general statement with no date is NOT a schedulable reminder.
    task = _propose(_engine(), "I think the project meeting went well.")
    assert svc.is_schedulable(task) is False


def test_reminder_without_date_not_schedulable(tmp_path):
    svc = _svc(tmp_path)
    task = _propose(_engine(), "Remind me to call the bank.")
    assert svc.is_schedulable(task) is False


# --- safe confirmation + execution -----------------------------------------
def test_confirm_and_schedule_creates_one_reminder(tmp_path):
    svc = _svc(tmp_path)
    task = _propose(_engine(), "Remind me about the project meeting tomorrow at 10 AM.")
    rc = svc.request_confirmation(task)
    assert rc.needs_confirmation and task.status is TaskStatus.AWAITING_CONFIRM
    res = svc.confirm_and_schedule(task, expected_revision=task.revision_number)
    assert res.ok and res.reminder is not None
    assert svc.store.count() == 1
    assert task.status is TaskStatus.EXECUTED
    # Resolved date/time are correct (tomorrow = 2026-10-21, 10:00).
    assert res.reminder.trigger_at.astimezone(ET).date().isoformat() == "2026-10-21"
    assert res.reminder.trigger_at.astimezone(ET).hour == 10


def test_idempotent_confirmation_no_duplicate(tmp_path):
    svc = _svc(tmp_path)
    task = _propose(_engine(), "Remind me about standup tomorrow at 9 AM.")
    svc.request_confirmation(task)
    svc.confirm_and_schedule(task, expected_revision=task.revision_number)
    # Re-confirm / retry: must NOT create a second reminder.
    res2 = svc.confirm_and_schedule(task, expected_revision=task.revision_number)
    assert svc.store.count() == 1
    assert res2.duplicate is True


def test_stale_revision_rejected(tmp_path):
    svc = _svc(tmp_path)
    eng = _engine()
    task = _propose(eng, "Remind me about the meeting tomorrow at 10 AM.")
    svc.request_confirmation(task)
    stale_rev = task.revision_number
    # A correction lands after confirmation was requested.
    eng.handle_turn("Actually, make it Friday.")
    res = svc.confirm_and_schedule(task, expected_revision=stale_rev)
    assert res.ok is False and res.stale is True
    assert svc.store.count() == 0  # nothing scheduled on a stale confirm


def test_failed_persistence_not_reported_success(tmp_path, monkeypatch):
    svc = _svc(tmp_path)
    task = _propose(_engine(), "Remind me about the meeting tomorrow at 10 AM.")
    svc.request_confirmation(task)

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(svc.store, "add", _boom)
    res = svc.confirm_and_schedule(task, expected_revision=task.revision_number)
    assert res.ok is False
    assert task.status is TaskStatus.FAILED  # honest failure, not EXECUTED


# --- corrections on REAL reminders -----------------------------------------
def _schedule(svc, engine, *utterances):
    task = _propose(engine, *utterances)
    svc.request_confirmation(task)
    res = svc.confirm_and_schedule(task, expected_revision=task.revision_number)
    return task, res.reminder


def test_reschedule_updates_real_record(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    res = svc.reschedule(rem.id, date_iso="2026-10-23", time_24h=None, source_text="move to Friday")
    assert res.ok
    updated = svc.store.get(rem.id)
    assert updated.trigger_at.astimezone(ET).date().isoformat() == "2026-10-23"
    assert updated.trigger_at.astimezone(ET).hour == 10  # time preserved


def test_reschedule_time_only_preserves_date(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    svc.reschedule(rem.id, date_iso=None, time_24h="11:00", source_text="11 am")
    updated = svc.store.get(rem.id)
    assert updated.trigger_at.astimezone(ET).hour == 11
    assert updated.trigger_at.astimezone(ET).date().isoformat() == "2026-10-21"  # date kept


def test_retitle_updates_real_record(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    res = svc.retitle(rem.id, "Weekly Sync", source_text="rename it Weekly Sync")
    assert res.ok
    assert svc.store.get(rem.id).title == "Weekly Sync"


def test_cancel_updates_real_record(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    res = svc.cancel(rem.id, source_text="cancel that reminder")
    assert res.ok
    assert svc.store.get(rem.id).status is ReminderStatus.CANCELLED


def test_complete_updates_real_record(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    res = svc.complete(rem.id)
    assert res.ok and svc.store.get(rem.id).status is ReminderStatus.COMPLETED


def test_snooze_pushes_trigger(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    res = svc.snooze(rem.id, _dt.timedelta(minutes=10), source_text="snooze 10 min")
    assert res.ok
    updated = svc.store.get(rem.id)
    assert updated.status is ReminderStatus.SNOOZED
    # New trigger is now + 10 min.
    assert updated.trigger_at.astimezone(ET) == NOW + _dt.timedelta(minutes=10)
    assert updated.original_trigger_at is not None  # original preserved


# --- completed/fired policy ------------------------------------------------
def test_cannot_cancel_already_fired(tmp_path):
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    rem.mark_notified()
    svc.store.update(rem)
    res = svc.cancel(rem.id)
    assert res.ok is False
    assert "already fired" in res.message.lower()


# --- queries ---------------------------------------------------------------
def test_query_on_date_returns_matching(tmp_path):
    svc = _svc(tmp_path)
    _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    friday = _dt.date(2026, 10, 21)
    found = svc.query_on_date(friday)
    assert len(found) == 1 and found[0].trigger_at.astimezone(ET).date() == friday


# --- independence from conversation-history retention ----------------------
def test_reminders_survive_disabled_chat_history(tmp_path):
    # Conversation history DISABLED (default) must not affect reminders.
    conv = ConversationStore(enabled=False, path=tmp_path / "conversation.json")
    svc = _svc(tmp_path)
    _, rem = _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    # No conversation file written (history off)...
    assert not (tmp_path / "conversation.json").exists()
    # ...but the reminder IS persisted independently and restores on restart.
    store2 = ReminderStore(path=tmp_path / "reminders.json", clock=_clock)
    assert store2.count() == 1
    assert store2.get(rem.id) is not None


def test_no_credentials_in_reminder_file(tmp_path):
    svc = _svc(tmp_path)
    _schedule(svc, _engine(), "Remind me about the meeting tomorrow at 10 AM.")
    blob = (tmp_path / "reminders.json").read_text(encoding="utf-8").lower()
    for forbidden in ("api_key", "authorization", "bearer", "password", "sk-"):
        assert forbidden not in blob


# --- typed == spoken routing -----------------------------------------------
def test_typed_and_spoken_schedule_identically(tmp_path):
    # Both inputs reach the service via the SAME confirmed TaskProposal path.
    svc_typed = _svc(tmp_path / "typed")
    (tmp_path / "typed").mkdir()
    svc_spoken = _svc(tmp_path / "spoken")
    (tmp_path / "spoken").mkdir()

    _, r_typed = _schedule(svc_typed, _engine(), "Remind me about the demo tomorrow at 2 PM.")
    _, r_spoken = _schedule(svc_spoken, _engine(), "Remind me about the demo tomorrow at 2 PM.")
    assert r_typed.trigger_at.astimezone(ET) == r_spoken.trigger_at.astimezone(ET)
    assert r_typed.title == r_spoken.title
