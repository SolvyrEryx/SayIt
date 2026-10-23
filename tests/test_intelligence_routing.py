"""Unified-intelligence orchestration, privacy, and routing tests."""

from __future__ import annotations

import datetime as _dt

import pytest

from sayit.core.conversation import ConversationEngine
from sayit.core.conversation import (
    CloudPolicy,
    Destination,
    Interaction,
    IntelligenceOrchestrator,
    classify_interaction,
)

TODAY = _dt.date(2026, 10, 14)


def _orch(cloud_enabled, provider_available, cloud_reply_fn=None):
    eng = ConversationEngine(today=TODAY)
    policy = CloudPolicy(cloud_enabled=cloud_enabled, provider_available=provider_available)
    return IntelligenceOrchestrator(eng, policy, cloud_reply_fn=cloud_reply_fn)


# --- classification (destination-based, deterministic) ----------------------
def test_classification_is_destination_based():
    assert classify_interaction(Destination.FOREGROUND) is Interaction.DICTATION
    assert classify_interaction(Destination.NOTE) is Interaction.NOTE
    assert classify_interaction(Destination.CHAT) is Interaction.CONVERSATION


def test_dictation_isolation_scratch_that_not_reinterpreted():
    # Ordinary dictation -> DICTATION, regardless of content containing a
    # correction-like phrase. It never becomes a CONVERSATION turn.
    assert classify_interaction(Destination.FOREGROUND) is Interaction.DICTATION


# --- cloud gating -----------------------------------------------------------
def test_cloud_disabled_uses_local_reply():
    o = _orch(cloud_enabled=False, provider_available=True,
              cloud_reply_fn=lambda t, c: "CLOUD")
    r = o.handle_conversation_turn("Remind me about the meeting tomorrow.")
    assert r.used_cloud is False
    assert "not enabled" in r.cloud_skipped_reason.lower()
    assert "CLOUD" not in r.text


def test_cloud_enabled_but_provider_unavailable():
    o = _orch(cloud_enabled=True, provider_available=False,
              cloud_reply_fn=lambda t, c: "CLOUD")
    r = o.handle_conversation_turn("Remind me tomorrow.")
    assert r.used_cloud is False
    assert "provider" in r.cloud_skipped_reason.lower()


def test_cloud_permitted_uses_provider():
    seen = {}
    def reply(text, ctx):
        seen["text"] = text
        seen["ctx"] = ctx
        return "Sure — reminder set."
    o = _orch(cloud_enabled=True, provider_available=True, cloud_reply_fn=reply)
    r = o.handle_conversation_turn("Remind me about the meeting tomorrow.")
    assert r.used_cloud is True
    assert r.text == "Sure — reminder set."
    # Minimal context only: the effective task, NOT raw history/clipboard/audio.
    assert set(seen["ctx"].keys()) <= {"task"}
    assert "slots" in seen["ctx"]["task"]


def test_provider_failure_preserves_local_state_and_reply():
    from sayit.core.conversation.state import SlotName

    def boom(text, ctx):
        raise RuntimeError("timeout")
    o = _orch(cloud_enabled=True, provider_available=True, cloud_reply_fn=boom)
    r = o.handle_conversation_turn("Remind me about the meeting on Friday.")
    assert r.used_cloud is False
    assert "failed" in r.cloud_skipped_reason.lower()
    # The local task state survived the provider failure.
    task = o._engine.state.active_task()
    assert task is not None
    assert task.get(SlotName.DATE) == "2026-10-16"


def test_clarification_short_circuits_cloud():
    from sayit.core.conversation.state import SlotName

    calls = []
    o = _orch(cloud_enabled=True, provider_available=True,
              cloud_reply_fn=lambda t, c: calls.append(1) or "CLOUD")
    # Create ambiguity: two open tasks.
    o._engine.handle_turn("Schedule a meeting on Friday.")
    o._engine.state.new_task()
    o._engine.state.tasks[-1].set_slot(SlotName.GOAL, "reminder", source_text="seed")
    r = o.handle_conversation_turn("Move that to Saturday.")
    assert r.needs_clarification is True
    assert calls == []  # no cloud call when we must clarify


# --- minimal context never leaks -------------------------------------------
def test_minimal_context_excludes_everything_but_task():
    o = _orch(cloud_enabled=True, provider_available=True)
    r = o._engine.handle_turn("Remind me tomorrow.")
    ctx = o._minimal_context(r)
    assert list(ctx.keys()) == ["task"]
    # No transcript turns, no notes, no clipboard.
    assert "turns" not in ctx and "notes" not in ctx and "clipboard" not in ctx
