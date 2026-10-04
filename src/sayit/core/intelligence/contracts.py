"""Phase 8H shared contracts for the SayIt intelligence layer.

These are the *smallest* abstractions needed to let the independent 8B-8G
engines be orchestrated centrally without any of them rewriting ``app.py``, the
worker, or settings. They reuse the existing explainability primitive
(:class:`~sayit.core.transcript_processor.Change`) rather than inventing a
parallel one.

Nothing here performs text processing; these are plain data carriers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..transcript_processor import Change


class IntentCategory(str, Enum):
    """What an utterance was deterministically determined to be.

    Only the categories actually used by the orchestrator are defined. ``str``
    mixin for stable, readable logging/serialization.
    """

    DICTATE = "dictate"            # ordinary dictation (default / fallback)
    VOICE_EDIT = "voice_edit"      # 8B: modify recent output
    SNIPPET = "snippet"            # 8C: expand a saved snippet
    STRUCTURE = "structure"        # 8G: structural/dictation commands
    DEVELOPER_FORMAT = "developer_format"  # 8D: explicit identifier casing / code block


@dataclass
class IntentResult:
    """The resolved intent for an utterance plus any engine-specific payload.

    - ``category``: the winning intent.
    - ``confidence``: a coarse deterministic signal in {0.0, 1.0}. Phase 8 uses
      binary confidence on purpose (strong evidence -> act; otherwise dictate),
      per the global safety principle. Kept as a float for future headroom.
    - ``payload``: opaque, engine-defined extra data (e.g. the resolved snippet,
      the parsed edit operation). The orchestrator does not interpret it beyond
      passing it to the owning engine.
    - ``reason``: short human string for explainability/logging.
    """

    category: IntentCategory = IntentCategory.DICTATE
    confidence: float = 0.0
    payload: Optional[object] = None
    reason: str = ""

    @property
    def is_command(self) -> bool:
        return self.category is not IntentCategory.DICTATE


@dataclass
class IntelligenceResult:
    """The outcome of running the intelligence layer over one utterance.

    - ``text``: the text that should ultimately be produced for this utterance
      (already transformed by whichever engine won, but BEFORE the existing
      6G/6I/6J + optional LLM pipeline, unless ``skip_correction`` is set).
    - ``intent``: the resolved intent.
    - ``changes``: explainable Change records accumulated by the engines.
    - ``replaces_recent_output``: True for a voice edit — the orchestrator/app
      must REPLACE the most recent inserted output rather than append. The
      ``text`` field then holds the full, coherent replacement for the recent
      editable unit.
    - ``replaced_span_text``: for a voice edit, the exact prior text being
      superseded (so the app can decide how to reconcile with what is on screen).
    - ``skip_correction``: when True (snippets, code blocks), the downstream
      6G/6I correction + structured formatting is skipped for this text because
      applying prose/technical normalization to a literal snippet or code block
      would corrupt it. User vocabulary (6J) and LLM still follow the normal
      policy decided by the caller.
    - ``suppressed``: True when the whole utterance was consumed by a command
      that produces no insertable text on its own (reserved; currently unused).
    """

    text: str
    intent: IntentResult = field(default_factory=IntentResult)
    changes: List[Change] = field(default_factory=list)
    replaces_recent_output: bool = False
    replaced_span_text: Optional[str] = None
    skip_correction: bool = False
    suppressed: bool = False

    def add_change(self, category: str, original: str, replacement: str, rule: str) -> None:
        self.changes.append(
            Change(category=category, original=original, replacement=replacement, rule=rule)
        )
