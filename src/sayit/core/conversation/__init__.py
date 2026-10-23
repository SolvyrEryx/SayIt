"""Conversational intelligence for SayIt.

This package implements multi-turn conversational state, deterministic
self-correction / intent revision, and a safe task-proposal lifecycle. It is
local-first and LLM-optional: the deterministic engine handles the required
correction patterns, slot updates, conflict/recency resolution and ambiguity
detection without any network call. An optional LLM may assist interpretation
but is never the sole authority over task state, permissions, or whether an
external side effect has occurred.

Nothing here performs shell/filesystem/autonomous actions.
"""

from .state import (
    ConversationState,
    Revision,
    SlotName,
    TaskProposal,
    TaskStatus,
)
from .corrections import (
    CorrectionKind,
    CorrectionSignal,
    detect_correction,
)
from .engine import ConversationEngine, TurnResult
from .voice_controller import ChatVoiceController, ChatVoiceState
from .store import ConversationStore
from .orchestrator import (
    AssistantReply,
    CloudDecision,
    CloudPolicy,
    ConversationOrchestrator,
    Destination,
    Interaction,
    IntelligenceOrchestrator,
    classify_interaction,
)

__all__ = [
    "ConversationState",
    "Revision",
    "SlotName",
    "TaskProposal",
    "TaskStatus",
    "CorrectionKind",
    "CorrectionSignal",
    "detect_correction",
    "ConversationEngine",
    "TurnResult",
    "ChatVoiceController",
    "ChatVoiceState",
    "ConversationStore",
    "AssistantReply",
    "CloudDecision",
    "CloudPolicy",
    "ConversationOrchestrator",
    "Destination",
    "Interaction",
    "IntelligenceOrchestrator",
    "classify_interaction",
]
