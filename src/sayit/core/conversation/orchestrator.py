"""Unified conversational intelligence orchestration (Workstream A).

One execution architecture, no global Online/Offline switch. The orchestrator
decides, deterministically and without any LLM call, how a CONVERSATION turn
should be handled based on its DESTINATION (where the user is directing input),
runs the local ConversationEngine (authoritative), then — only when permitted —
enriches the reply with a cloud provider.

This lives in the ``conversation`` package and is deliberately SEPARATE from the
pre-existing deterministic post-ASR ``core.intelligence`` orchestrator (voice
editing); the two do not collide.

Interaction kinds:
  DICTATION  — ordinary voice typing into the foreground app (fast path; never
               touched by the conversation/self-correction engine).
  NOTE       — explicit Dictate-to-Note routing (existing behaviour).
  CONVERSATION — a chat-assistant turn; the ConversationEngine owns task state.

Cloud use is gated by a CloudPolicy mirroring SayIt's existing opt-in: a
provider being *configured* does not authorize transmission. Classification is
destination-based, NOT content-based, so a dictated "scratch that" is never
reinterpreted as an assistant command.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Interaction(str, Enum):
    DICTATION = "dictation"
    NOTE = "note"
    CONVERSATION = "conversation"


class Destination(str, Enum):
    FOREGROUND = "foreground"   # ordinary dictation target
    NOTE = "note"               # Dictate-to-Note active
    CHAT = "chat"               # the conversational assistant panel


@dataclass(frozen=True)
class CloudDecision:
    allowed: bool
    reason: str = ""


class CloudPolicy:
    """Deterministic cloud-eligibility policy (no network, no LLM).

    BOTH ``cloud_enabled`` (explicit opt-in) and ``provider_available`` must be
    true for cloud use — a configured key alone never authorizes transmission.
    """

    def __init__(self, *, cloud_enabled: bool, provider_available: bool):
        self._cloud_enabled = cloud_enabled
        self._provider_available = provider_available

    def decide(self) -> CloudDecision:
        if not self._cloud_enabled:
            return CloudDecision(False, "Cloud processing is not enabled by the user.")
        if not self._provider_available:
            return CloudDecision(False, "No cloud provider is configured/available.")
        return CloudDecision(True, "Cloud processing permitted by policy.")


def classify_interaction(destination: Destination) -> Interaction:
    """Deterministically map a destination to an interaction kind.

    Destination-based (not content-based) so ordinary dictation is never
    reinterpreted as an assistant instruction.
    """
    if destination is Destination.CHAT:
        return Interaction.CONVERSATION
    if destination is Destination.NOTE:
        return Interaction.NOTE
    return Interaction.DICTATION


@dataclass
class AssistantReply:
    text: str
    used_cloud: bool = False
    cloud_skipped_reason: str = ""
    needs_clarification: bool = False


class ConversationOrchestrator:
    """Coordinates local conversation handling + optional cloud enrichment.

    NEVER calls an LLM to decide whether to call an LLM. Runs the local
    ConversationEngine for every turn (it owns task state), then — only if the
    CloudPolicy permits — asks a provider to phrase a nicer reply. A provider
    failure/denial leaves the locally-correct conversation state intact.
    """

    def __init__(
        self,
        engine,  # ConversationEngine
        cloud_policy: CloudPolicy,
        *,
        cloud_reply_fn: Optional[Callable[[str, dict], str]] = None,
        store=None,  # Optional ConversationStore for privacy-gated persistence
    ):
        self._engine = engine
        self._policy = cloud_policy
        self._cloud_reply_fn = cloud_reply_fn
        self._store = store
        # Restore a prior conversation ONLY when retention is enabled (the store
        # returns an empty state otherwise — no hidden second history).
        if self._store is not None and getattr(self._store, "enabled", False):
            try:
                restored = self._store.load()
                if restored.turns or restored.tasks:
                    self._engine.state = restored
            except Exception:
                pass  # never let restore failure break a fresh conversation

    def handle_conversation_turn(self, text: str) -> AssistantReply:
        result = self._engine.handle_turn(text)

        reply = self._compose_reply(result, text)
        # Persist after the turn, gated by retention opt-in (no-op if disabled).
        if self._store is not None:
            try:
                self._store.save(self._engine.state)
            except Exception:
                pass
        return reply

    def _compose_reply(self, result, text: str) -> AssistantReply:
        if result.needs_clarification:
            return AssistantReply(text=result.clarification, needs_clarification=True)

        base_reply = self._local_reply(result)

        decision = self._policy.decide()
        if not decision.allowed or self._cloud_reply_fn is None:
            return AssistantReply(
                text=base_reply, used_cloud=False,
                cloud_skipped_reason=decision.reason if not decision.allowed else
                "No cloud reply function wired.",
            )
        try:
            ctx = self._minimal_context(result)
            enriched = self._cloud_reply_fn(text, ctx)
            if enriched and enriched.strip():
                return AssistantReply(text=enriched.strip(), used_cloud=True)
        except Exception:
            return AssistantReply(
                text=base_reply, used_cloud=False,
                cloud_skipped_reason="Cloud provider failed; used local reply.",
            )
        return AssistantReply(text=base_reply, used_cloud=False,
                              cloud_skipped_reason="Empty cloud reply; used local.")

    # -- helpers --------------------------------------------------------
    def _local_reply(self, result) -> str:
        task = result.task
        if task is None:
            return "Okay."
        eff = task.effective()
        slots = eff["slots"]
        bits = []
        if slots.get("goal"):
            bits.append(f"goal={slots['goal']}")
        if slots.get("date"):
            bits.append(f"date={slots['date']}")
        elif slots.get("date_phrase"):
            bits.append(f"date={slots['date_phrase']} (unresolved)")
        if slots.get("time"):
            bits.append(f"time={slots['time']}")
        if eff["requirements"]:
            bits.append("includes: " + ", ".join(eff["requirements"]))
        summary = "; ".join(bits) if bits else "updated"
        return f"Current task ({eff['status']}, rev {eff['revision']}): {summary}."

    def _minimal_context(self, result) -> dict:
        """The NARROW context sent to a provider — the effective task only.

        Deliberately excludes raw audio, clipboard, screen, full notes, and the
        unrelated conversation history.
        """
        if result.task is None:
            return {}
        return {"task": result.task.effective()}


# Backwards-friendly alias (some call sites referred to it generically).
IntelligenceOrchestrator = ConversationOrchestrator
