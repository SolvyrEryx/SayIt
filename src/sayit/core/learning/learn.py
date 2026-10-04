"""Deterministic correction-candidate construction (Phase 8F).

Given the raw ASR transcript and the user's explicit corrected text, compute a
minimal spoken->written candidate by diffing the two token sequences. Only a
clear, bounded difference yields a candidate (strong evidence); otherwise no
candidate is offered.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional

from ..transcript_processor import VocabularyEntry


@dataclass
class CorrectionCandidate:
    """A proposed spoken->written mapping awaiting explicit user confirmation."""

    spoken: str
    written: str
    rule: str = "remember_correction"

    def prompt_text(self) -> str:
        return f'Remember "{self.spoken}" \u2192 "{self.written}"?'


# Guard rails: a candidate's spoken side must be short (a term, not a sentence)
# and must actually differ. These keep the feature from creating huge or
# accidental rules.
_MAX_SPOKEN_TOKENS = 4


def build_candidate(raw: str, corrected: str) -> Optional[CorrectionCandidate]:
    """Diff ``raw`` vs ``corrected`` into a single bounded candidate, or None.

    Deterministic (uses difflib on lowercased token sequences). Returns None
    when:
    - either side is empty,
    - they are equal,
    - the differing region is empty on the spoken side,
    - or the differing spoken region exceeds ``_MAX_SPOKEN_TOKENS`` (too broad
      to be a safe single rule).
    """
    if not raw or not corrected:
        return None
    raw_s = raw.strip()
    cor_s = corrected.strip()
    if not raw_s or not cor_s or raw_s == cor_s:
        return None

    raw_tokens = raw_s.split()
    cor_tokens = cor_s.split()
    sm = SequenceMatcher(a=[t.lower() for t in raw_tokens], b=[t.lower() for t in cor_tokens])

    spoken_parts: List[str] = []
    written_parts: List[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        spoken_parts.extend(raw_tokens[i1:i2])
        written_parts.extend(cor_tokens[j1:j2])

    spoken = " ".join(spoken_parts).strip()
    written = " ".join(written_parts).strip()
    if not spoken or not written:
        return None
    if len(spoken.split()) > _MAX_SPOKEN_TOKENS:
        return None
    if spoken.lower() == written.lower():
        return None
    return CorrectionCandidate(spoken=spoken, written=written)


def make_vocabulary_entry(candidate: CorrectionCandidate) -> VocabularyEntry:
    """Create a 6J vocabulary entry from a confirmed candidate.

    The entry is tagged with the 'learned' category so it is visible/editable in
    the Vocabulary UI and distinguishable from manually-added entries.
    """
    return VocabularyEntry(
        spoken=candidate.spoken,
        written=candidate.written,
        enabled=True,
        category="learned",
    )


def suppression_key(candidate: CorrectionCandidate) -> str:
    """A stable key identifying a candidate for 'Never' suppression."""
    return f"{candidate.spoken.lower()}=>{candidate.written.lower()}"


def is_suppressed(candidate: CorrectionCandidate, never_list: List[str]) -> bool:
    if not never_list:
        return False
    return suppression_key(candidate) in set(never_list)
