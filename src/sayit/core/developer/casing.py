"""Explicit identifier casing commands (Phase 8D).

Grammar: ``<words> , <casing> case`` where the casing command is a strongly
anchored TRAILING clause. The command is only recognized when:

- it is at the END of the utterance, and
- it is one of the four known styles, and
- there are words before it to form an identifier.

Otherwise the utterance is returned unchanged (is_command=False), so ordinary
sentences that merely mention "snake case" are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

STYLE_CAMEL = "camel"
STYLE_SNAKE = "snake"
STYLE_KEBAB = "kebab"
STYLE_PASCAL = "pascal"

# Trailing, anchored: optional comma/space, "<style> case" at end of utterance.
_CASING_RE = re.compile(
    r"^(?P<words>.+?)\s*,?\s+(?P<style>camel|snake|kebab|pascal)\s+case\s*[.!?]?$",
    re.IGNORECASE,
)


@dataclass
class CasingResult:
    is_command: bool
    identifier: str = ""
    style: str = ""
    rule: str = ""


def _tokenize_words(words: str) -> List[str]:
    # Keep only alphanumeric word tokens; drop punctuation. Lowercase for
    # deterministic recombination.
    raw = re.findall(r"[A-Za-z0-9]+", words)
    return [w.lower() for w in raw if w]


def _apply_style(tokens: List[str], style: str) -> str:
    if not tokens:
        return ""
    if style == STYLE_SNAKE:
        return "_".join(tokens)
    if style == STYLE_KEBAB:
        return "-".join(tokens)
    if style == STYLE_CAMEL:
        return tokens[0] + "".join(t.capitalize() for t in tokens[1:])
    if style == STYLE_PASCAL:
        return "".join(t.capitalize() for t in tokens)
    return " ".join(tokens)


def detect_casing_command(utterance: str) -> CasingResult:
    """Parse an explicit trailing casing command. Pure/deterministic."""
    if not utterance or not utterance.strip():
        return CasingResult(is_command=False)
    m = _CASING_RE.match(utterance.strip())
    if not m:
        return CasingResult(is_command=False)
    style = m.group("style").lower()
    tokens = _tokenize_words(m.group("words"))
    if not tokens:
        return CasingResult(is_command=False)
    identifier = _apply_style(tokens, style)
    if not identifier:
        return CasingResult(is_command=False)
    return CasingResult(
        is_command=True,
        identifier=identifier,
        style=style,
        rule=f"{style}_case",
    )
