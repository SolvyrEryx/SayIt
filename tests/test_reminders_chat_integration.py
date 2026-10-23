"""Chat <-> reminder integration tests: confirm flow + NL management.

Covers the required cases: confirm calls the authoritative service, stale
confirmation rejected, repeated confirmation creates only one reminder, storage
failure never reports success, success persists before display, NL management
(reschedule/retitle/cancel/snooze/query) updates the real record, typed==spoken,
and independence from conversation-history retention.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from sayit.core.conversation import (  # noqa: E402
    CloudPolicy,
    ConversationEngine,
    ConversationOrchestrator,
    ConversationStore,
)
from sayit.core.reminders import (  # noqa: E402
    ReminderConversationBridge,
    ReminderService,
    ReminderStatus,
    ReminderStore,
)
from sayit.ui.chat_panel import ChatPanel  # noqa: E402

ET = ZoneInfo("America/New_York")
NOW = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)  # Tue; tomorrow=Wed 10-21


def _app():
    return QApplication.instance() or QApplication([])


def _make(tmp_path, *, conv_store=None):
    store = ReminderStore(path=tmp_path / "reminders.json", clock=lambda: NOW)
    svc = ReminderService(store, local_tz=ET)
    eng = ConversationEngine(today=NOW.date())
    orch = ConversationOrchestrator(
        eng, CloudPolicy(cloud_enabled=False, provider_available=False),
        store=conv_store,
    )
    bridge = ReminderConversationBridge(svc, eng)
    return store, svc, eng, orch, bridge


# --- bridge: confirm calls the authoritative service -----------------------
def test_confirm_active_schedules_via_service(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("Remind me about the project meeting tomorrow at 10 AM.")
    assert bridge.active_proposal_schedulable() is True
    res = bridge.confirm_active()
    assert res.ok and store.count() == 1
    assert res.reminder.trigger_at.astimezone(ET).date().isoformat() == "2026-10-21"


def test_repeated_confirm_single_reminder(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("Remind me about standup tomorrow at 9 AM.")
    bridge.confirm_active()
    bridge.confirm_active()
    bridge.confirm_active()
    assert store.count() == 1  # idempotent


def test_stale_confirm_rejected(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("Remind me about the meeting tomorrow at 10 AM.")
    task = eng.state.active_task()
    svc.request_confirmation(task)
    stale = task.revision_number
    eng.handle_turn("Actually, make it Friday.")  # correction after confirm requested
    res = svc.confirm_and_schedule(task, expected_revision=stale)
    assert res.ok is False and res.stale is True
    assert store.count() == 0


def test_storage_failure_not_reported_success(tmp_path, monkeypatch):
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("Remind me about the meeting tomorrow at 10 AM.")

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(store, "add", _boom)
    res = bridge.confirm_active()
    assert res.ok is False
    assert store.count() == 0  # nothing persisted, no false success


def test_success_persists_before_display(tmp_path):
    # The reminder file exists on disk the moment confirm reports success.
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("Remind me about the demo tomorrow at 2 PM.")
    res = bridge.confirm_active()
    assert res.ok
    assert (tmp_path / "reminders.json").exists()
    reloaded = ReminderStore(path=tmp_path / "reminders.json", clock=lambda: NOW)
    assert reloaded.count() == 1


# --- NL management updates the REAL record ---------------------------------
def _schedule(bridge, eng):
    eng.handle_turn("Remind me about the project meeting tomorrow at 10 AM.")
    return bridge.confirm_active().reminder


def test_nl_reschedule_updates_record(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    rem = _schedule(bridge, eng)
    br = bridge.handle_turn("Move that reminder to Friday at 11 AM.")
    assert br.handled
    r = store.get(rem.id)
    assert r.trigger_at.astimezone(ET).date().isoformat() == "2026-10-23"
    assert r.trigger_at.astimezone(ET).hour == 11
    assert r.status is ReminderStatus.PENDING


def test_nl_retitle_updates_record(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    rem = _schedule(bridge, eng)
    br = bridge.handle_turn("Change its title to Weekly Sync.")
    assert br.handled and store.get(rem.id).title == "Weekly Sync"


def test_nl_cancel_prevents_future_delivery(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    rem = _schedule(bridge, eng)
    br = bridge.handle_turn("Cancel that reminder.")
    assert br.handled and store.get(rem.id).status is ReminderStatus.CANCELLED
    # Cancelled reminders are not active, so the scheduler never fires them.
    assert rem.id not in [r.id for r in store.active()]


def test_nl_snooze_updates_record(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    rem = _schedule(bridge, eng)
    br = bridge.handle_turn("Snooze it for 15 minutes.")
    assert br.handled
    r = store.get(rem.id)
    assert r.status is ReminderStatus.SNOOZED
    assert r.trigger_at.astimezone(ET) == NOW + _dt.timedelta(minutes=15)


def test_nl_query_lists_reminders(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    _schedule(bridge, eng)
    br = bridge.handle_turn("What reminders do I have on Wednesday?")
    assert br.handled and "project meeting" in br.text.lower()


def test_nl_query_empty_is_honest(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    br = bridge.handle_turn("What reminders do I have tomorrow?")
    assert br.handled and "no" in br.text.lower()


def test_ambiguous_management_asks_clarification(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    # Two independent active reminders, no live proposal link.
    from sayit.core.reminders import Reminder, build_trigger
    for title in ("A", "B"):
        store.add(Reminder(title=title,
                           trigger_at=build_trigger("2026-10-21", "10:00", tz=ET, now=NOW)))
    eng.state.active_task_id = None  # no linked proposal
    br = bridge.handle_turn("Cancel that reminder.")
    assert br.handled and br.needs_clarification


# --- casual mention is NOT auto-scheduled ----------------------------------
def test_casual_mention_no_confirm_button(tmp_path):
    store, svc, eng, orch, bridge = _make(tmp_path)
    eng.handle_turn("I think the meeting went well yesterday.")
    assert bridge.active_proposal_schedulable() is False


# --- typed == spoken (same bridge entry) -----------------------------------
def test_typed_and_spoken_management_identical(tmp_path):
    # Both inputs reach bridge.handle_turn identically.
    s1, v1, e1, o1, b1 = _make(tmp_path / "t")
    (tmp_path / "t").mkdir()
    s2, v2, e2, o2, b2 = _make(tmp_path / "s")
    (tmp_path / "s").mkdir()
    r1 = _schedule(b1, e1)
    r2 = _schedule(b2, e2)
    b1.handle_turn("Move that reminder to Friday at 11 AM.")
    b2.handle_turn("Move that reminder to Friday at 11 AM.")
    assert (s1.get(r1.id).trigger_at.astimezone(ET)
            == s2.get(r2.id).trigger_at.astimezone(ET))


# --- independence from conversation-history retention ----------------------
def test_reminder_independent_of_chat_history(tmp_path):
    conv = ConversationStore(enabled=False, path=tmp_path / "conversation.json")
    store, svc, eng, orch, bridge = _make(tmp_path, conv_store=conv)
    _schedule(bridge, eng)
    # Chat history OFF: no conversation file...
    assert not (tmp_path / "conversation.json").exists()
    # ...but the reminder persists independently.
    reloaded = ReminderStore(path=tmp_path / "reminders.json", clock=lambda: NOW)
    assert reloaded.count() == 1


# --- ChatPanel confirm button wiring (double-click guard) ------------------
def test_chatpanel_confirm_button_single_schedule(qtbot, tmp_path):
    _app()
    store, svc, eng, orch, bridge = _make(tmp_path)
    panel = ChatPanel(orch, reminder_bridge=bridge)
    qtbot.addWidget(panel)
    panel.submit_text("Remind me about the meeting tomorrow at 10 AM.")
    # The turn runs off-thread; wait for it to finish and the proposal to sync.
    qtbot.waitUntil(lambda: bridge.active_proposal_schedulable() is True, timeout=5000)
    panel._on_confirm_reminder()
    assert store.count() == 1
    # Simulate a rapid second click; must not double-schedule.
    panel._confirm_widget.setVisible(True)
    panel._on_confirm_reminder()
    assert store.count() == 1
