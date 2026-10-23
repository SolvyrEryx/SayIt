"""Safe-action lifecycle + integration tests."""

from __future__ import annotations

import datetime as _dt

import pytest

from sayit.core.conversation import ConversationEngine
from sayit.core.conversation.safe_action import ActionCoordinator, ActionError
from sayit.core.conversation.state import SlotName, TaskStatus

TODAY = _dt.date(2026, 10, 14)


def _task_ready():
    e = ConversationEngine(today=TODAY)
    e.handle_turn("Remind me about the meeting on Friday at 10 AM.")
    return e, e.state.active_task()


def test_confirm_requires_all_required_slots():
    e, task = _task_ready()
    coord = ActionCoordinator()
    # Missing nothing (goal/date/time present) -> can move to awaiting confirm.
    ready = coord.request_confirmation(task, required=["goal", "date", "time"])
    assert ready is True
    assert task.status is TaskStatus.AWAITING_CONFIRM


def test_confirm_blocks_when_required_missing():
    e = ConversationEngine(today=TODAY)
    e.handle_turn("Remind me about the meeting.")  # no date/time
    task = e.state.active_task()
    coord = ActionCoordinator()
    assert coord.request_confirmation(task, required=["goal", "date", "time"]) is False
    assert task.status is TaskStatus.DRAFT


def test_execute_requires_confirmation_and_current_revision():
    e, task = _task_ready()
    coord = ActionCoordinator()
    coord.request_confirmation(task, required=["goal", "date", "time"])
    rev_at_confirm = task.revision_number
    # A correction after confirmation bumps the revision -> stale execute fails.
    e.handle_turn("Actually, Saturday.")
    with pytest.raises(ActionError, match="Stale revision"):
        coord.execute(task, lambda t: "effect-1",
                      expected_revision=rev_at_confirm, confirmed=True)


def test_execute_is_idempotent_no_duplicate_effect():
    e, task = _task_ready()
    coord = ActionCoordinator()
    coord.request_confirmation(task, required=["goal", "date", "time"])
    calls = []
    def cap(t):
        calls.append(1)
        return "effect-xyz"
    r1 = coord.execute(task, cap, expected_revision=task.revision_number, confirmed=True)
    assert r1.ok and r1.effect_id == "effect-xyz"
    # A second execute must NOT run the capability again (idempotent).
    r2 = coord.execute(task, cap, expected_revision=task.revision_number, confirmed=True)
    assert r2.duplicate_suppressed is True
    assert r2.effect_id == "effect-xyz"
    assert calls == [1]


def test_execute_without_confirmation_refused():
    e, task = _task_ready()
    coord = ActionCoordinator()
    coord.request_confirmation(task, required=["goal", "date", "time"])
    with pytest.raises(ActionError, match="confirmation"):
        coord.execute(task, lambda t: "x",
                      expected_revision=task.revision_number, confirmed=False)


def test_revision_increments_on_every_change():
    e, task = _task_ready()
    r0 = task.revision_number
    e.handle_turn("Actually, Saturday.")
    assert task.revision_number > r0


# --- persistence (state is serializable via effective()) --------------------
def test_task_effective_is_json_serializable():
    import json
    e, task = _task_ready()
    snapshot = json.dumps(task.effective())
    restored = json.loads(snapshot)
    assert restored["slots"]["date"] == "2026-10-16"
    assert restored["slots"]["time"] == "10:00"


# --- no regression in technical-term correction -----------------------------
def test_technical_correction_still_works():
    from sayit.core.transcript_processor import correct_transcript
    res = correct_transcript("we deployed with git hub actions")
    assert "GitHub" in res.text  # deterministic tech correction intact


def test_semantic_layer_does_not_touch_technical_corrector():
    # The conversation engine must not import/alter the technical corrector's
    # behaviour. A correction phrase routed to the engine changes task state,
    # not prose. Here, the technical corrector leaves "scratch that" prose as-is.
    from sayit.core.transcript_processor import correct_transcript
    res = correct_transcript("please scratch that line from the budget")
    assert "scratch that" in res.text.lower()
