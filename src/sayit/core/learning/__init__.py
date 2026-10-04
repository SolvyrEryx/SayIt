"""Phase 8F explicit "Remember this correction?" learning.

This is the ONLY learning path in SayIt and it is strictly explicit:

- A candidate rule is computed by deterministically diffing an ASR transcript
  against a correction the user has explicitly provided (e.g. edited in a
  prompt). Nothing is observed passively — no typed text, clipboard, browser,
  editor, or application content is ever read.
- A candidate is only OFFERED to the user; it is never applied automatically.
- The vocabulary entry is created only when the user explicitly chooses
  "Remember". "Not now" does nothing. "Never" records a suppression so the same
  deterministic candidate is not offered again.

Reuses the 6J ``VocabularyEntry`` type; it does not create a parallel vocab.
"""

from .learn import (
    CorrectionCandidate,
    build_candidate,
    make_vocabulary_entry,
    suppression_key,
    is_suppressed,
)

__all__ = [
    "CorrectionCandidate",
    "build_candidate",
    "make_vocabulary_entry",
    "suppression_key",
    "is_suppressed",
]
