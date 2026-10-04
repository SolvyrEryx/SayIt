"""Phase 9G — explicit personalization as a ranking prior.

Converts the user's EXPLICIT vocabulary (6J ``VocabularyEntry``) and explicitly
remembered corrections (8F) into knowledge candidates that strengthen ranking —
but NEVER as an unconditional override. The 9F ranker's threshold / margin /
ambiguity / ordinary-language gates still apply; personalization only raises a
candidate's prior (source confidence "6j" = 1.0, plus the retriever's user
boost).

Hard rules enforced here:
- EXPLICIT ONLY. Input is the user's saved vocabulary (which is only ever
  created by an explicit Remember/add action in the existing app). This module
  never observes transcripts, edits, or behavior. There is no learning path.
- LIFECYCLE. inspect / disable / delete / clear operate on the existing
  settings-backed vocabulary list; no new hidden store is created.
- GRACEFUL FALLBACK. With zero personalization the system behaves exactly as
  the global model.
"""

from __future__ import annotations

from typing import List, Optional

from ..transcript_processor.vocabulary import VocabularyEntry, entries_from_any
from .models import Domain, KnowledgeTerm


def vocab_entry_to_term(entry: VocabularyEntry) -> KnowledgeTerm:
    """Map an explicit user vocabulary entry to a high-priority KnowledgeTerm.

    canonical = written form (what the user wants emitted); spoken form = the
    dictated form. Source "6j" => source_confidence 1.0 in the ranker. A small
    relevance bump reflects explicit user intent (usage_count-aware but capped).
    """
    usage = max(0, int(getattr(entry, "usage_count", 0) or 0))
    relevance = min(1.0, 0.8 + 0.02 * usage)  # explicit + lightly usage-aware
    return KnowledgeTerm(
        canonical=entry.written or entry.spoken,
        spoken_variants=(entry.spoken,),
        category="user_vocabulary",
        domain=Domain.DEVELOPER,
        source="6j",
        relevance=round(relevance, 3),
        metadata={"canonical_confidence": "1.0", "ambiguity_class": "none",
                  "user_category": entry.category or "", "usage_count": str(usage)},
    )


def personalized_terms(custom_vocabulary: Optional[List[dict]],
                       legacy_replacements=None) -> List[KnowledgeTerm]:
    """Build personalization ranking-prior terms from the user's explicit
    vocabulary. ENABLED entries only. Returns [] when there is no personalization
    (graceful fallback to the global model)."""
    entries = entries_from_any(custom_vocabulary, legacy_replacements)
    return [vocab_entry_to_term(e) for e in entries if e.enabled and e.is_valid()]


class PersonalizationStore:
    """Thin lifecycle wrapper over the existing settings-backed vocabulary.

    Does NOT introduce new persistence; it reads/writes the same
    ``custom_vocabulary`` list the 6J Vocabulary UI already manages, so the
    user's existing inspect/edit/delete controls remain the single source of
    truth. Provided here so 9G lifecycle semantics are explicit and testable.
    """

    def __init__(self, custom_vocabulary: Optional[List[dict]] = None):
        self._items: List[dict] = list(custom_vocabulary or [])

    def inspect(self) -> List[dict]:
        return list(self._items)

    def enabled_terms(self) -> List[KnowledgeTerm]:
        return personalized_terms(self._items)

    def disable(self, spoken: str) -> int:
        n = 0
        for it in self._items:
            if (it.get("spoken", "").lower() == (spoken or "").lower()) and it.get("enabled", True):
                it["enabled"] = False
                n += 1
        return n

    def delete(self, spoken: str) -> int:
        before = len(self._items)
        self._items = [it for it in self._items
                       if it.get("spoken", "").lower() != (spoken or "").lower()]
        return before - len(self._items)

    def clear(self) -> None:
        self._items = []

    def export(self) -> List[dict]:
        """Return the current list for persisting back to settings."""
        return list(self._items)
