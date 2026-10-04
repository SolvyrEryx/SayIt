"""Deterministic voice-edit parser for Phase 8B.

Two editing situations are handled, both strongly anchored:

1. **Within-utterance backtrack** - the single utterance contains content and a
   trailing correction, e.g.:
       "I'll meet you at five. Actually six."   -> "I'll meet you at six."
       "Install Docker. Scratch that. Install Podman." -> "Install Podman."
   This is resolved purely from the utterance text (no prior output needed).

2. **Cross-utterance edit** - the utterance is *only* a command that refers to
   the most recent output held in the OutputBuffer, e.g.:
       "scratch that"                 -> delete the recent output
       "delete the last sentence"     -> drop the last sentence of recent output
       "replace five with six"        -> substitute within recent output
       "change Docker to Podman"      -> substitute within recent output

Safety (false positives are worse than false negatives):

- A command is only recognized when it matches an explicit, anchored pattern at
  the START (cross-utterance) or as a clearly separated trailing clause
  (within-utterance). Command words buried in prose do NOT trigger.
- "Actually, I agree." / "Scratch paper is useful." / "Delete that file later."
  are ordinary prose and are returned unchanged (is_edit=False).
- When a command has no safe target (e.g. "scratch that" with an empty buffer),
  nothing is done and the utterance is treated as ordinary dictation.

The parser is pure: ``detect_voice_edit(utterance, buffer_text)`` has no side
effects and is fully deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Operations
OP_REPLACE_RECENT = "replace_recent"   # supersede the recent output with new_text
OP_DELETE_RECENT = "delete_recent"     # remove the recent output entirely
OP_DELETE_LAST_SENTENCE = "delete_last_sentence"
OP_SUBSTITUTE = "substitute"           # replace X with Y inside recent output


@dataclass
class VoiceEditResult:
    """Outcome of parsing an utterance as a potential voice edit.

    - ``is_edit``: True only when a safe, anchored edit was recognized.
    - ``operation``: one of the OP_* constants (when is_edit).
    - ``new_text``: the resulting full text for the edited unit (when the edit
      replaces/produces output). For a pure deletion with nothing left, this is
      "" and ``replaces_recent`` is True.
    - ``replaces_recent``: True when the edit modifies the most recent OUTPUT
      (cross-utterance). False for a within-utterance backtrack, where the
      utterance itself is simply resolved before its first insertion.
    - ``rule``: explainability tag.
    - ``summary``: short human description, e.g. 'Replaced "five" with "six"'.
    """

    is_edit: bool
    operation: Optional[str] = None
    new_text: str = ""
    replaces_recent: bool = False
    rule: str = ""
    summary: str = ""


# --- helpers ----------------------------------------------------------------

def _norm_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_trailing_punct(token: str) -> str:
    return token.strip().strip(".,!?;:").strip()


def _recase_after_replacement(result: str) -> str:
    """Capitalize the first alphabetic character of the result if the original
    started capitalized-looking. Conservative: only fixes a leading lowercase
    letter at position 0. Avoids broad rewriting."""
    if result and result[0].islower():
        return result[0].upper() + result[1:]
    return result


# --- within-utterance backtrack ---------------------------------------------

# "<something>. Actually <replacement>." -> keep <something head> + replacement.
# Anchored: "actually" must FOLLOW a sentence boundary (., !, ?) and be the start
# of the final clause. A leading "Actually, ..." (comma, no preceding sentence)
# is NOT an edit.
_ACTUALLY_RE = re.compile(
    r"^(?P<head>.*[.!?])\s+actually\s+(?P<rep>[^.!?]+?)\s*[.!?]?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# "<A>. Scratch that. <B>" -> "<B>". The "scratch that" / "delete that" clause
# must be a standalone sentence between two others (or at the end).
_SCRATCH_MID_RE = re.compile(
    r"^(?P<a>.*?[.!?])\s*(?:scratch that|delete that)\s*[.!?]\s*(?P<b>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _try_within_utterance(utterance: str) -> Optional[VoiceEditResult]:
    text = utterance.strip()

    # "A. Scratch that. B" -> B
    m = _SCRATCH_MID_RE.match(text)
    if m:
        b = _norm_spaces(m.group("b"))
        if b:
            return VoiceEditResult(
                is_edit=True,
                operation=OP_REPLACE_RECENT,
                new_text=b,
                replaces_recent=False,
                rule="backtrack_scratch_inline",
                summary="Discarded the retracted phrase",
            )

    # "<head>. Actually <rep>." -> replace the last sentence's tail.
    m = _ACTUALLY_RE.match(text)
    if m:
        head = m.group("head").strip()
        rep = _norm_spaces(m.group("rep"))
        if not rep:
            return None
        rebuilt = _rebuild_actually(head, rep)
        if rebuilt is not None:
            return VoiceEditResult(
                is_edit=True,
                operation=OP_REPLACE_RECENT,
                new_text=rebuilt,
                replaces_recent=False,
                rule="backtrack_actually_inline",
                summary="Applied an 'actually' correction",
            )
    return None


def _rebuild_actually(head: str, replacement: str) -> Optional[str]:
    """Given the head ('I'll meet you at five.') and the replacement ('six'),
    build the corrected sentence by swapping the LAST token of the final
    sentence with the replacement.

    Conservative: only replaces the final word (or final number) of the last
    sentence. If the structure is not a simple final-token swap, returns None so
    the utterance is treated as ordinary dictation rather than guessed at.
    """
    # Split head into sentences keeping terminators.
    sentences = re.findall(r"[^.!?]*[.!?]+", head)
    if not sentences:
        return None
    last = sentences[-1].strip()
    term = last[-1]  # . ! ?
    body = last[:-1].rstrip()
    # Replace the final whitespace-delimited token of the body.
    tokens = body.split()
    if not tokens:
        return None
    tokens[-1] = replacement
    new_last = " ".join(tokens) + term
    # Reassemble: all prior sentences unchanged, final sentence rebuilt.
    prior = [s.strip() for s in sentences[:-1]]
    rebuilt = " ".join(prior + [new_last])
    return _norm_spaces(rebuilt)


# --- cross-utterance commands -----------------------------------------------

# Pure-command utterances. Must match the WHOLE utterance (anchored start/end),
# optionally with trailing punctuation, so command words inside prose never fire.
_SCRATCH_RE = re.compile(r"^(?:scratch that|delete that)\s*[.!?]?$", re.IGNORECASE)
_DELETE_LAST_SENTENCE_RE = re.compile(
    r"^(?:delete|remove) the last sentence\s*[.!?]?$", re.IGNORECASE
)
_REPLACE_RE = re.compile(
    r"^replace\s+(?P<x>.+?)\s+with\s+(?P<y>.+?)\s*[.!?]?$", re.IGNORECASE
)
_CHANGE_RE = re.compile(
    r"^change\s+(?P<x>.+?)\s+to\s+(?P<y>.+?)\s*[.!?]?$", re.IGNORECASE
)


def _try_cross_utterance(utterance: str, buffer_text: Optional[str]) -> Optional[VoiceEditResult]:
    text = utterance.strip()
    has_buffer = bool(buffer_text and buffer_text.strip())

    if _SCRATCH_RE.match(text):
        if not has_buffer:
            return None  # no safe target -> ordinary dictation
        return VoiceEditResult(
            is_edit=True,
            operation=OP_DELETE_RECENT,
            new_text="",
            replaces_recent=True,
            rule="delete_recent",
            summary="Deleted the last output",
        )

    if _DELETE_LAST_SENTENCE_RE.match(text):
        if not has_buffer:
            return None
        remaining = _drop_last_sentence(buffer_text)
        return VoiceEditResult(
            is_edit=True,
            operation=OP_DELETE_LAST_SENTENCE,
            new_text=remaining,
            replaces_recent=True,
            rule="delete_last_sentence",
            summary="Deleted the last sentence",
        )

    for pat, rule in ((_REPLACE_RE, "replace_phrase"), (_CHANGE_RE, "change_phrase")):
        m = pat.match(text)
        if m:
            if not has_buffer:
                return None
            x = _strip_trailing_punct(m.group("x"))
            y = _strip_trailing_punct(m.group("y"))
            if not x:
                return None
            # Whole-word, case-insensitive substitution within the recent output.
            pattern = r"\b" + re.escape(x) + r"\b"
            if not re.search(pattern, buffer_text, flags=re.IGNORECASE):
                # Target not present -> no safe edit; treat as dictation.
                return None
            new_text = re.sub(pattern, y, buffer_text, flags=re.IGNORECASE)
            return VoiceEditResult(
                is_edit=True,
                operation=OP_SUBSTITUTE,
                new_text=_norm_spaces(new_text),
                replaces_recent=True,
                rule=rule,
                summary=f'Replaced "{x}" with "{y}"',
            )
    return None


def _drop_last_sentence(text: str) -> str:
    sentences = re.findall(r"[^.!?]*[.!?]+|\S[^.!?]*$", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return ""
    return " ".join(sentences[:-1]).strip()


# --- public entry point ------------------------------------------------------

def detect_voice_edit(
    utterance: str, buffer_text: Optional[str] = None
) -> VoiceEditResult:
    """Parse ``utterance`` as a possible voice edit.

    Returns a VoiceEditResult with ``is_edit=False`` when the utterance is
    ordinary speech (the safe default). Pure and deterministic.
    """
    if not utterance or not utterance.strip():
        return VoiceEditResult(is_edit=False)

    # Cross-utterance pure commands first: they are the most strongly anchored
    # (whole-utterance match) and have the clearest intent.
    cross = _try_cross_utterance(utterance, buffer_text)
    if cross is not None:
        return cross

    # Within-utterance backtrack (content + trailing correction).
    within = _try_within_utterance(utterance)
    if within is not None:
        return within

    return VoiceEditResult(is_edit=False)
