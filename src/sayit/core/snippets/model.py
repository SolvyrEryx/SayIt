"""Snippet data model + persistence helpers (Phase 8C).

Mirrors the shape and conventions of the 6J ``VocabularyEntry`` so the UI and
persistence feel identical, but is a distinct type because snippets differ
semantically (explicit trigger -> block expansion, multiline, text-only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class Snippet:
    """One user-created snippet.

    - ``trigger``: the spoken trigger phrase (may be multi-word).
    - ``expansion``: the literal text to insert (may be multiline). Inserted
      verbatim; never executed.
    - ``enabled``: disabled snippets are kept but never applied.
    - ``category``: free-form user label.
    - ``inline``: when True the trigger may expand mid-utterance; when False
      (default, safest) the snippet only fires when the trigger is the entire
      utterance.
    - ``created_at`` / ``usage_count``: local metadata only; never transmitted.
    """

    trigger: str
    expansion: str = ""
    enabled: bool = True
    category: str = ""
    inline: bool = False
    created_at: str = ""
    usage_count: int = 0

    def __post_init__(self):
        self.trigger = (self.trigger or "").strip()
        self.expansion = self.expansion or ""
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def is_valid(self) -> bool:
        # A usable snippet needs a trigger and a non-empty expansion.
        return bool(self.trigger.strip()) and bool(self.expansion)

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "expansion": self.expansion,
            "enabled": self.enabled,
            "category": self.category,
            "inline": self.inline,
            "created_at": self.created_at,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snippet":
        return cls(
            trigger=str(data.get("trigger", "")),
            expansion=str(data.get("expansion", "")),
            enabled=bool(data.get("enabled", True)),
            category=str(data.get("category", "")),
            inline=bool(data.get("inline", False)),
            created_at=str(data.get("created_at", "")),
            usage_count=int(data.get("usage_count", 0) or 0),
        )


def snippets_from_any(raw: Optional[List[dict]]) -> List[Snippet]:
    """Build a snippet list from stored dicts, skipping malformed items."""
    out: List[Snippet] = []
    if not raw:
        return out
    for item in raw:
        try:
            if isinstance(item, dict):
                s = Snippet.from_dict(item)
            else:
                continue
            if s.is_valid():
                out.append(s)
        except Exception:
            continue
    return out


@dataclass
class SnippetConflicts:
    duplicates: List[str] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.duplicates)


def detect_snippet_conflicts(snippets: List[Snippet]) -> SnippetConflicts:
    """Report duplicate enabled triggers (deterministic longest-first means only
    one would ever apply)."""
    conflicts = SnippetConflicts()
    seen: Dict[str, int] = {}
    for s in snippets:
        if not (s.enabled and s.trigger.strip()):
            continue
        key = s.trigger.lower()
        seen[key] = seen.get(key, 0) + 1
    conflicts.duplicates = sorted({k for k, c in seen.items() if c > 1})
    return conflicts
