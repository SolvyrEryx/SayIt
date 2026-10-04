"""Phase 6J: user-controlled custom vocabulary (local, deterministic).

A spoken-form -> written-form mapping the user explicitly manages. This is NOT
automatic learning: nothing is added without an explicit user action, no
transcript is stored for learning, and nothing is sent anywhere.

The matching engine is adapted (conceptually) from the WritHer "Layer A" user
vocabulary: case-insensitive, whole-word, multi-word, longest-first. It is
reimplemented natively here on SayIt's own data model and returns explainable
Change records using the existing Phase 6G ``Change`` dataclass, so it fits the
existing transcript-processor pipeline.

Persistence uses SayIt's existing Pydantic/JSON settings (no SQLite dependency
is introduced): entries are stored as a list of plain dicts under the
``custom_vocabulary`` setting, with backward-compatible import from the legacy
``vocabulary_replacements`` list of (original, replacement) tuples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .technical_corrector import Change


@dataclass
class VocabularyEntry:
    """One user-controlled spoken->written mapping.

    - ``spoken``: the dictated form (may contain internal spaces for multi-word).
    - ``written``: the canonical output.
    - ``enabled``: disabled entries are kept but never applied.
    - ``category``: free-form user label (optional).
    - ``created_at``: ISO timestamp (set on creation).
    - ``usage_count``: incremented when the entry actually changes text. This is
      a local counter only; it is never transmitted.
    """

    spoken: str
    written: str
    enabled: bool = True
    category: str = ""
    created_at: str = ""
    usage_count: int = 0

    def __post_init__(self):
        self.spoken = (self.spoken or "").strip()
        self.written = self.written or ""
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return {
            "spoken": self.spoken,
            "written": self.written,
            "enabled": self.enabled,
            "category": self.category,
            "created_at": self.created_at,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VocabularyEntry":
        return cls(
            spoken=str(data.get("spoken", "")),
            written=str(data.get("written", "")),
            enabled=bool(data.get("enabled", True)),
            category=str(data.get("category", "")),
            created_at=str(data.get("created_at", "")),
            usage_count=int(data.get("usage_count", 0) or 0),
        )

    def is_valid(self) -> bool:
        # A usable entry needs a non-empty spoken form. Empty written form is
        # allowed (acts as a deletion of the spoken phrase).
        return bool(self.spoken.strip())


# --- loading / normalization ------------------------------------------------

def entries_from_any(
    custom_vocabulary: Optional[List[dict]],
    legacy_replacements: Optional[List[Tuple[str, str]]] = None,
) -> List[VocabularyEntry]:
    """Build the entry list from the new structured field, migrating the legacy
    (original, replacement) tuples when the new field is empty.

    Malformed items are skipped defensively (never crash dictation).
    """
    entries: List[VocabularyEntry] = []
    if custom_vocabulary:
        for item in custom_vocabulary:
            try:
                if isinstance(item, dict):
                    e = VocabularyEntry.from_dict(item)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    e = VocabularyEntry(spoken=str(item[0]), written=str(item[1]))
                else:
                    continue
                if e.is_valid():
                    entries.append(e)
            except Exception:
                continue
        return entries

    # Migration path: legacy tuples -> enabled entries.
    if legacy_replacements:
        for pair in legacy_replacements:
            try:
                spoken, written = pair[0], pair[1]
            except Exception:
                continue
            e = VocabularyEntry(spoken=str(spoken), written=str(written))
            if e.is_valid():
                entries.append(e)
    return entries


# --- conflict detection -----------------------------------------------------

@dataclass
class VocabularyConflicts:
    duplicates: List[str] = field(default_factory=list)  # same spoken form >1x
    overlaps: List[Tuple[str, str]] = field(default_factory=list)  # a is substr-phrase of b

    @property
    def has_any(self) -> bool:
        return bool(self.duplicates or self.overlaps)


def detect_conflicts(entries: List[VocabularyEntry]) -> VocabularyConflicts:
    """Detect duplicate and overlapping ENABLED spoken forms (deterministic).

    - duplicate: two enabled entries share the same spoken form (case-insensitive).
      With longest-first + first-wins, only one would ever apply, so this is
      surfaced to the user.
    - overlap: one enabled spoken form is a whole-word sub-phrase of another
      (e.g. "new" vs "new york"). This is not an error — longest-first resolves
      it deterministically — but it is reported so the user understands the
      precedence.
    """
    conflicts = VocabularyConflicts()
    enabled = [e for e in entries if e.enabled and e.spoken.strip()]

    seen: Dict[str, int] = {}
    for e in enabled:
        key = e.spoken.lower()
        seen[key] = seen.get(key, 0) + 1
    conflicts.duplicates = sorted({k for k, c in seen.items() if c > 1})

    # Overlap: whole-word sub-phrase containment.
    lowers = [e.spoken.lower() for e in enabled]
    for i, a in enumerate(lowers):
        for j, b in enumerate(lowers):
            if i == j or a == b:
                continue
            # Is `a` a whole-word sub-phrase of `b`?
            if re.search(r"\b" + re.escape(a) + r"\b", b):
                pair = (a, b)
                if pair not in conflicts.overlaps:
                    conflicts.overlaps.append(pair)
    conflicts.overlaps.sort()
    return conflicts


# --- matching engine --------------------------------------------------------

def apply_user_vocabulary(
    text: str, entries: List[VocabularyEntry]
) -> Tuple[str, List[Change], Dict[str, int]]:
    """Apply enabled vocabulary entries to ``text``.

    Semantics (adapted from WritHer Layer A, reimplemented natively):
    - case-insensitive, whole-word (``\\b`` boundaries);
    - multi-word spoken forms supported (internal spaces matched literally, with
      flexible whitespace so "new   york" still matches "new york");
    - deterministic longest-first precedence (longer spoken form wins), with
      ties broken by original order for stability;
    - disabled entries are skipped;
    - returns (new_text, changes, usage_delta) where usage_delta maps a spoken
      form to the number of substitutions it made (for local usage counting).

    Idempotent in practice: once a spoken form is rewritten to its written form,
    the written form no longer matches the spoken pattern (unless the user
    deliberately created a self-referential rule), so re-running is a no-op.
    """
    changes: List[Change] = []
    usage: Dict[str, int] = {}
    if not text or not entries:
        return text, changes, usage

    # Longest-first by spoken length; stable for equal lengths.
    ordered = sorted(
        [e for e in entries if e.enabled and e.spoken.strip()],
        key=lambda e: len(e.spoken),
        reverse=True,
    )

    for e in ordered:
        # Build a whole-word, case-insensitive pattern allowing flexible internal
        # whitespace between the words of a multi-word spoken form.
        words = e.spoken.split()
        if not words:
            continue
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
        count = 0

        def _repl(m, written=e.written, sp=e.spoken):
            nonlocal count
            count += 1
            return written

        new_text = re.sub(pattern, _repl, text, flags=re.IGNORECASE)
        if count > 0 and new_text != text:
            changes.append(
                Change(
                    category="user",
                    original=e.spoken,
                    replacement=e.written,
                    rule="user_vocabulary",
                )
            )
            usage[e.spoken] = usage.get(e.spoken, 0) + count
            text = new_text

    return text, changes, usage
