"""Phase 8B voice edit / backtrack.

A deterministic, strongly-anchored editing layer that can modify the most recent
SayIt output in response to explicit spoken commands. It is NOT free-form
natural-language editing and it never guesses: ambiguous input is returned as
ordinary dictation (the global safety principle).

Public API:
    OutputBuffer      - bounded in-memory record of recent output (no disk).
    VoiceEditResult   - outcome of attempting to parse/apply an edit.
    detect_voice_edit - pure parser (utterance + buffer -> VoiceEditResult).
"""

from .buffer import OutputBuffer
from .edit import VoiceEditResult, detect_voice_edit

__all__ = ["OutputBuffer", "VoiceEditResult", "detect_voice_edit"]
