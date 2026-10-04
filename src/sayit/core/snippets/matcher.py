"""Deterministic snippet matcher (Phase 8C).

Two modes, both text-only (the matcher returns text; it never executes
anything):

- ``match_snippet``: whole-utterance match. The utterance (ignoring surrounding
  whitespace and a single trailing . ! ?) must equal an enabled trigger
  (case-insensitive). This is the default and safest behavior — "my github"
  expands only when the user says exactly "my github".

- ``expand_inline``: longest-first, whole-word inline expansion using only
  snippets explicitly marked ``inline=True``. Mirrors the 6J matching
  discipline. Off unless the user opts a snippet into inline mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .model import Snippet


@dataclass
class SnippetMatch:
    snippet: Snippet
    expansion: str
    rule: str = "user_snippet"


def _normalize_utterance(text: str) -> str:
    t = (text or "").strip()
    # Drop a single trailing sentence terminator the ASR may have added.
    t = re.sub(r"[.!?]\s*$", "", t)
    return t.strip()


def match_snippet(
    utterance: str, snippets: List[Snippet]
) -> Optional[SnippetMatch]:
    """Return a whole-utterance snippet match, or None.

    Longest trigger first for determinism (so a more specific trigger wins if
    two enabled triggers both equal the utterance only via case). Equality is
    case-insensitive on the normalized utterance.
    """
    if not utterance or not snippets:
        return None
    norm = _normalize_utterance(utterance).lower()
    if not norm:
        return None
    enabled = [s for s in snippets if s.enabled and s.trigger.strip()]
    enabled.sort(key=lambda s: len(s.trigger), reverse=True)
    for s in enabled:
        if s.trigger.strip().lower() == norm:
            return SnippetMatch(snippet=s, expansion=s.expansion)
    return None


def expand_inline(
    text: str, snippets: List[Snippet]
) -> Tuple[str, List[SnippetMatch]]:
    """Expand inline-enabled snippet triggers within ``text``.

    Whole-word, case-insensitive, longest-first. Only snippets with
    ``inline=True`` participate. Returns (new_text, matches). Single-pass per
    trigger; the inserted expansion is NOT re-scanned, preventing recursive
    expansion loops.
    """
    matches: List[SnippetMatch] = []
    if not text or not snippets:
        return text, matches
    inline = [s for s in snippets if s.enabled and s.inline and s.trigger.strip()]
    inline.sort(key=lambda s: len(s.trigger), reverse=True)

    result = text
    for s in inline:
        words = s.trigger.split()
        if not words:
            continue
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
        if re.search(pattern, result, flags=re.IGNORECASE):
            # Replace all occurrences; the expansion is literal text and is not
            # re-scanned by subsequent iterations' searches against the ORIGINAL
            # trigger patterns (a different trigger could still match it, but we
            # iterate a fixed snapshot of triggers, so no unbounded recursion).
            result = re.sub(
                pattern, lambda m, e=s.expansion: e, result, flags=re.IGNORECASE
            )
            matches.append(SnippetMatch(snippet=s, expansion=s.expansion))
    return result, matches
