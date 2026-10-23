"""Deterministic detection of conversational self-corrections.

This is NOT a bag of literal string replacements. It classifies a user message
into a small, consistent set of correction *kinds* and extracts the clause that
carries the new intent, so the engine can apply it to the active task's slots.

Kinds:
  REPLACE  — supersede earlier value(s): "scratch that, Friday", "actually 3pm",
             "no make it X", "change that to X", "I meant X", "not Y — X"
  ADD      — additive: "also include X", "one more thing: X", "add X"
  REMOVE   — drop a requirement: "remove X", "forget the X", "drop X"
  CANCEL   — cancel the whole pending task: "cancel that", "forget it"
  UNDO     — revert the previous correction: "undo that", "forget the last change"
  NONE     — ordinary content, no correction signal

Robustness: leading conversational fillers ("um", "uh", "like"), repeated words
and minor punctuation are tolerated; a bare hesitation is never treated as a
correction. Detection is case-insensitive and anchored to correction *cues*, so
ordinary prose that merely contains a word like "actually" mid-sentence is far
less likely to be misread than a cue at a clause boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CorrectionKind(str, Enum):
    NONE = "none"
    REPLACE = "replace"
    TITLE = "title"
    ADD = "add"
    REMOVE = "remove"
    CANCEL = "cancel"
    UNDO = "undo"


@dataclass(frozen=True)
class CorrectionSignal:
    kind: CorrectionKind
    # The clause carrying the new/affected content (what to apply). For CANCEL
    # and UNDO this is usually empty.
    payload: str
    # The cue that triggered detection (for debugging/explanation).
    cue: str = ""


_FILLERS = r"(?:\b(?:um+|uh+|er+|like|you know|i think|well)\b[,\s]*)*"

# Cancel / undo are whole-task operations; check them first (most specific).
_CANCEL_RE = re.compile(
    r"^\s*" + _FILLERS + r"(cancel (?:that|it|this)|forget it|never mind|"
    r"nevermind|drop it|scrap (?:that|it|the whole thing))\b",
    re.IGNORECASE,
)
_UNDO_RE = re.compile(
    r"^\s*" + _FILLERS + r"(undo (?:that|the (?:last|previous) (?:change|correction))|"
    r"forget the last (?:change|correction)|revert that)\b",
    re.IGNORECASE,
)

# Replacement cues. Capture the trailing clause as the new value.
_REPLACE_CUES = [
    r"scratch that[,\.\s-]*",
    r"actually[,\.\s-]+",
    r"sorry[, ]+i meant[,\.\s-]*",
    r"i meant[,\.\s-]*",
    r"no[, ]+make (?:it|that)[,\.\s-]*",
    r"make (?:it|that)[,\.\s-]*",
    r"change (?:that|it|the \w+) to[,\.\s-]*",
    r"change (?:that|it) to[,\.\s-]*",
    r"move (?:that|it|this)(?: one)? to[,\.\s-]*",
    r"push (?:that|it|this) to[,\.\s-]*",
    r"instead[,\.\s-]+",
    r"let me rephrase[,\.\s-]*",
    r"wait[, ]+not [^,]+[,\.\s-]+",
    r"not [^,]+[,\s]+(?:but )?",
    r"no[,\.\s-]+",
]
_REPLACE_RE = re.compile(
    r"(?:^|[\.\u2014,;-]\s*)" + _FILLERS + r"(" + "|".join(_REPLACE_CUES) + r")",
    re.IGNORECASE,
)

# Additive cues.
_ADD_RE = re.compile(
    r"(?:^|[\.\u2014,;-]\s*)" + _FILLERS
    + r"(also(?: include| add)?|one more thing(?: to add)?[:,\s]*|and also|plus|add)\b",
    re.IGNORECASE,
)

# Removal cues.
_REMOVE_RE = re.compile(
    r"(?:^|[\.\u2014,;-]\s*)" + _FILLERS
    + r"(remove|drop|forget|without|take out|get rid of)\b",
    re.IGNORECASE,
)

# Title/subject rename cues. These target the task's TITLE (subject slot) and
# capture the NEW title VERBATIM (case preserved), so "change its title to
# Project Review" sets the title to exactly "Project Review". Supports the
# possessive "its"/"the" forms the generic replace cue intentionally omits.
_TITLE_RE = re.compile(
    r"(?:change|set|update|make)\s+(?:its|the|it'?s)\s+(?:title|name|subject)\s+to\b\s*"
    r"|(?:rename|retitle)\s+(?:it|that|this)\s+to\b\s*"
    r"|(?:the\s+)?(?:title|name|subject)\s+(?:should\s+be|to)\b\s*"
    r"|(?:call|title|name)\s+(?:it|that|this)\b\s*",
    re.IGNORECASE,
)


def _clause_after(text: str, match: re.Match) -> str:
    """Everything after the matched cue, trimmed of leading punctuation/fillers."""
    tail = text[match.end():].strip()
    tail = re.sub(r"^[,\.\u2014;:\-\s]+", "", tail)
    tail = re.sub(r"^" + _FILLERS, "", tail, flags=re.IGNORECASE).strip()
    return tail


def _title_value(text: str, match: re.Match) -> str:
    """The new title after a title cue, VERBATIM (case preserved).

    Trims surrounding quotes and a single trailing sentence period, but does not
    alter the title's internal casing ("Project Review" stays as given).
    """
    tail = text[match.end():].strip()
    tail = tail.strip("\"'\u201c\u201d\u2018\u2019")
    tail = re.sub(r"[\.\s]+$", "", tail)
    return tail.strip()


def detect_correction(text: str) -> CorrectionSignal:
    """Classify ``text`` as a correction (or not). Deterministic, no network.

    Checks the most specific whole-task operations first (cancel/undo), then
    remove/add, then the general replacement cues.
    """
    if not text or not text.strip():
        return CorrectionSignal(CorrectionKind.NONE, "")

    stripped = text.strip()

    m = _CANCEL_RE.search(stripped)
    if m:
        return CorrectionSignal(CorrectionKind.CANCEL, "", m.group(1))

    m = _UNDO_RE.search(stripped)
    if m:
        return CorrectionSignal(CorrectionKind.UNDO, "", m.group(1))

    # Remove before add/replace so "remove the budget" isn't read as replace.
    m = _REMOVE_RE.search(stripped)
    if m:
        payload = _clause_after(stripped, m)
        if payload:
            return CorrectionSignal(CorrectionKind.REMOVE, payload, m.group(1))

    m = _ADD_RE.search(stripped)
    if m:
        payload = _clause_after(stripped, m)
        if payload:
            return CorrectionSignal(CorrectionKind.ADD, payload, m.group(1))

    # Title/subject rename BEFORE the generic replace: a title cue is specific
    # and must not be swallowed by a looser replacement pattern. An EMPTY title
    # ("change the title to") is still a TITLE signal with no payload so the
    # engine can ask for clarification rather than guessing.
    m = _TITLE_RE.search(stripped)
    if m:
        title = _title_value(stripped, m)
        return CorrectionSignal(CorrectionKind.TITLE, title, m.group(0).strip())

    m = _REPLACE_RE.search(stripped)
    if m:
        payload = _clause_after(stripped, m)
        if payload:
            return CorrectionSignal(CorrectionKind.REPLACE, payload, m.group(1).strip())

    return CorrectionSignal(CorrectionKind.NONE, stripped)
