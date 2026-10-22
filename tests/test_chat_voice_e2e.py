"""End-to-end voice-to-chat correction (Tests 1-7) + retention + serialization.

Spoken input is modeled by feeding the transcribed phrase to the orchestrator's
``handle_conversation_turn`` — the EXACT path the voice controller uses after
local transcription (ChatVoiceController.transcript_ready -> ChatPanel.submit_text
-> orchestrator). Typed and spoken input therefore share one code path, so these
tests prove "typed == spoken" revision behaviour. Deterministic ``today``.
"""

from __future__ import annotations

import datetime as _dt
import json

import pytest

from sayit.core.conversation import (
    CloudPolicy,
    ConversationEngine,
    ConversationOrchestrator,
    ConversationStore,
)
from sayit.core.conversation.state import ConversationState, SlotName, TaskStatus

TODAY = _dt.date(2026, 10, 14)  # Wednesday
FRIDAY = "2026-10-16"
SATURDAY = "2026-10-17"


def _orch(store=None):
    eng = ConversationEngine(today=TODAY)
    pol = CloudPolicy(cloud_enabled=False, provider_available=False)
    return ConversationOrchestrator(eng, pol, store=store)


def _speak(o, *utterances):
    """Simulate spoken turns (post-transcription) through the real path."""
    last = None
    for u in utterances:
        last = o.handle_conversation_turn(u)
    return last


# --- Test 1: correct a date (spoken) ---------------------------------------
def test_voice_test1_date_correction():
    o = _orch()
    _speak(o, "I have a meeting tomorrow.", "Scratch that, Friday.")
    task = o._engine.state.active_task()
    assert task.get(SlotName.DATE) == FRIDAY
    assert len(o._engine.state.tasks) == 1


# --- Test 2: correct a time (spoken) ---------------------------------------
def test_voice_test2_time_correction():
    o = _orch()
    _speak(o, "Set it for two PM.", "Actually, three PM.")
    task = o._engine.state.active_task()
    assert task.get(SlotName.TIME) == "15:00"
    assert len(o._engine.state.tasks) == 1


# --- Test 3: preserve unaffected fields ------------------------------------
def test_voice_test3_preserve_unaffected():
    o = _orch()
    _speak(o, "Remind me about the project meeting tomorrow at ten AM.", "Actually, Friday.")
    task = o._engine.state.active_task()
    assert task.get(SlotName.DATE) == FRIDAY
    assert task.get(SlotName.TIME) == "10:00"
    assert task.get(SlotName.GOAL) == "reminder"


# --- Test 4: multiple revisions --------------------------------------------
def test_voice_test4_multiple_revisions():
    o = _orch()
    _speak(o, "Friday at two.", "No, Saturday at four.")
    task = o._engine.state.active_task()
    assert task.get(SlotName.DATE) == SATURDAY
    assert task.get(SlotName.TIME) == "16:00"


# --- Test 5: clarification --------------------------------------------------
def test_voice_test5_clarification():
    o = _orch()
    o._engine.handle_turn("Schedule a meeting on Friday.")
    o._engine.state.new_task()
    o._engine.state.tasks[-1].set_slot(SlotName.GOAL, "reminder", source_text="seed")
    r = o.handle_conversation_turn("Move that to Friday.")
    assert r.needs_clarification is True


# --- Test 6: ordinary dictation isolation ----------------------------------
def test_voice_test6_dictation_isolation():
    from sayit.core.conversation import classify_interaction, Destination, Interaction
    # Foreground dictation is classified as DICTATION regardless of content, so
    # the conversation engine is never invoked for it.
    assert classify_interaction(Destination.FOREGROUND) is Interaction.DICTATION
    # A fresh engine that only ever saw dictation has no conversational task.
    o = _orch()
    assert o._engine.state.active_task() is None


# --- Test 7: cancellation (stale result cannot overwrite) ------------------
def test_voice_test7_cancellation_and_stale():
    from sayit.core.conversation.safe_action import ActionCoordinator
    o = _orch()
    _speak(o, "Remind me tomorrow.")
    task = o._engine.state.active_task()
    stale_rev = task.revision_number
    _speak(o, "Actually, Friday.")
    coord = ActionCoordinator()
    assert coord.is_result_current(task, stale_rev) is False
    assert coord.is_result_current(task, task.revision_number) is True
    # Cancelling marks the pending task cancelled; no side effect.
    _speak(o, "Cancel that.")
    assert o._engine.state.active_task().status is TaskStatus.CANCELLED


# --- typed == spoken (same API) --------------------------------------------
def test_typed_and_spoken_produce_identical_state():
    o1 = _orch()
    _speak(o1, "Remind me about the meeting tomorrow.", "Scratch that, Friday.")
    o2 = _orch()
    # "Typed" uses the identical handle_conversation_turn entry point.
    o2.handle_conversation_turn("Remind me about the meeting tomorrow.")
    o2.handle_conversation_turn("Scratch that, Friday.")
    assert (o1._engine.state.active_task().get(SlotName.DATE)
            == o2._engine.state.active_task().get(SlotName.DATE) == FRIDAY)


# --- retention: disabled (default) -----------------------------------------
def test_retention_disabled_no_file(tmp_path):
    store = ConversationStore(enabled=False, path=tmp_path / "conv.json")
    o = _orch(store=store)
    _speak(o, "Remind me tomorrow.")
    assert not (tmp_path / "conv.json").exists()  # nothing persisted
    # In-memory conversation still usable while open.
    assert o._engine.state.active_task() is not None


# --- retention: enabled persists + restores --------------------------------
def test_retention_enabled_persists_and_restores(tmp_path):
    p = tmp_path / "conv.json"
    store = ConversationStore(enabled=True, path=p)
    o = _orch(store=store)
    _speak(o, "Remind me about the meeting on Friday.")
    assert p.exists()
    # New orchestrator with an enabled store restores prior state.
    store2 = ConversationStore(enabled=True, path=p)
    o2 = _orch(store=store2)
    assert o2._engine.state.active_task() is not None
    assert o2._engine.state.active_task().get(SlotName.DATE) == FRIDAY


def test_retention_enabled_file_not_read_when_disabled(tmp_path):
    p = tmp_path / "conv.json"
    ConversationStore(enabled=True, path=p).save(_orch()._engine.state)  # write something
    # A DISABLED store must not read the existing file (no hidden history).
    disabled = ConversationStore(enabled=False, path=p)
    restored = disabled.load()
    assert restored.turns == [] and restored.tasks == []


def test_clear_history_removes_store(tmp_path):
    p = tmp_path / "conv.json"
    store = ConversationStore(enabled=True, path=p)
    o = _orch(store=store)
    _speak(o, "Remind me tomorrow.")
    assert p.exists()
    store.clear()
    assert not p.exists()


# --- serialization safety ---------------------------------------------------
def test_serialize_roundtrip():
    o = _orch()
    _speak(o, "Remind me about the meeting on Friday at 10 AM.")
    data = o._engine.state.to_dict()
    blob = json.dumps(data)  # must be JSON-serializable
    restored = ConversationState.from_dict(json.loads(blob))
    assert restored.active_task() is not None
    assert restored.active_task().get(SlotName.DATE) == FRIDAY


def test_executed_status_not_replayable_after_restore():
    o = _orch()
    _speak(o, "Remind me about the meeting on Friday.")
    task = o._engine.state.active_task()
    task.mark_executed(effect_id="effect-123")
    data = o._engine.state.to_dict()
    restored = ConversationState.from_dict(data)
    rt = restored.active_task()
    # Restored task is inert: no executed status, no effect id (no replay).
    assert rt.status is not TaskStatus.EXECUTED
    assert rt.executed_effect_id is None
    assert rt.idempotency_key is None


def test_malformed_state_loads_safely(tmp_path):
    p = tmp_path / "conv.json"
    p.write_text("{ this is not valid json ]", encoding="utf-8")
    store = ConversationStore(enabled=True, path=p)
    state = store.load()
    assert isinstance(state, ConversationState)
    assert state.tasks == []
    # A backup of the corrupt file was kept.
    assert (tmp_path / "conv.corrupt.bak").exists()


def test_no_credentials_in_serialized_state():
    o = _orch()
    _speak(o, "Remind me about the meeting on Friday.")
    blob = json.dumps(o._engine.state.to_dict()).lower()
    for forbidden in ("api_key", "authorization", "bearer", "sk-", "password"):
        assert forbidden not in blob
