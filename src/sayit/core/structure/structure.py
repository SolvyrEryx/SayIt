"""Smart structure parser (Phase 8G). Pure/deterministic.

Only strongly-anchored patterns produce structure; anything else is returned
unchanged (is_structure=False).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Whole-utterance structure keywords.
_NEW_PARAGRAPH_RE = re.compile(r"^new paragraph\s*[.!?]?$", re.IGNORECASE)
_NEW_LINE_RE = re.compile(r"^new line\s*[.!?]?$", re.IGNORECASE)

# Ordinal list: the utterance is a sequence of clauses each introduced by a
# leading ordinal word. Require at least TWO ordinals in order to treat it as a
# list (one "first" alone is just prose).
_ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth",
             "seventh", "eighth", "ninth", "tenth"]
_ORDINAL_ALT = "|".join(_ORDINALS)
# Split points: an ordinal word at the START of the utterance or following
# whitespace, used as a leading item marker.
_ORDINAL_LEAD_RE = re.compile(
    rf"(?:^|\s)(?P<ord>{_ORDINAL_ALT})\s+", re.IGNORECASE
)


@dataclass
class StructureResult:
    is_structure: bool
    text: str = ""
    rule: str = ""
    standalone: bool = False  # True for pure break commands (no content)


def _ordinal_index(word: str) -> int:
    return _ORDINALS.index(word.lower())


def _try_ordinal_list(utterance: str) -> Optional[StructureResult]:
    text = utterance.strip()
    # Find all leading ordinals and their positions.
    matches = list(_ORDINAL_LEAD_RE.finditer(text))
    if len(matches) < 2:
        return None
    # The ordinals must appear in strictly increasing order starting at 'first'
    # (strong evidence that the speaker is enumerating). This rejects prose that
    # merely contains an ordinal or two out of order.
    indices = [_ordinal_index(m.group("ord")) for m in matches]
    if indices[0] != 0:
        return None
    for a, b in zip(indices, indices[1:]):
        if b != a + 1:
            return None
    # The first ordinal should be at or very near the start of the utterance.
    if matches[0].start("ord") > 0:
        return None

    # Carve items between successive ordinal markers.
    items: List[str] = []
    for i, m in enumerate(matches):
        start = m.end("ord")
        end = matches[i + 1].start("ord") if i + 1 < len(matches) else len(text)
        item = text[start:end].strip()
        # Drop a trailing connector/punct left dangling before the next ordinal.
        item = re.sub(r"[,.;:!?]+$", "", item).strip()
        if not item:
            return None
        # Reject if an item still contains an ordinal word (e.g. a trailing
        # "... but third" where "third" never led its own item). That signals
        # connective prose rather than a clean enumeration.
        if re.search(rf"\b(?:{_ORDINAL_ALT})\b", item, flags=re.IGNORECASE):
            return None
        # Capitalize first letter for a clean list item.
        item = item[0].upper() + item[1:] if item else item
        items.append(item)

    if len(items) < 2:
        return None
    numbered = "\n".join(f"{i + 1}. {it}" for i, it in enumerate(items))
    return StructureResult(
        is_structure=True, text=numbered, rule="ordinal_list", standalone=False
    )


def detect_structure(utterance: str) -> StructureResult:
    """Parse an explicit structure command. Pure/deterministic."""
    if not utterance or not utterance.strip():
        return StructureResult(is_structure=False)
    text = utterance.strip()

    if _NEW_PARAGRAPH_RE.match(text):
        return StructureResult(
            is_structure=True, text="\n\n", rule="new_paragraph", standalone=True
        )
    if _NEW_LINE_RE.match(text):
        return StructureResult(
            is_structure=True, text="\n", rule="new_line", standalone=True
        )

    ordinal = _try_ordinal_list(text)
    if ordinal is not None:
        return ordinal

    return StructureResult(is_structure=False)
