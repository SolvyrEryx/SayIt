"""Local, deterministic post-ASR technical correction + conservative formatting.

Runs entirely locally with no network, no model, and no transcript logging. It
produces an explainable result (raw text, final text, list of changes) and is:

- conservative: only well-registered technical aliases / clearly-structured
  expressions are changed; ordinary prose is left alone;
- idempotent: ``normalize(normalize(x)).text == normalize(x).text``;
- order-stable: whitespace -> technical aliases -> spelled acronyms ->
  structured formatting -> explicit user vocabulary.

The corrector never fabricates sentences and contains no benchmark-specific
hard-coded transcripts; it operates only on reusable technical entities and
structured expressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .tech_vocabulary import SPELLED_ACRONYMS, TECH_ENTITIES
from .structured_formatter import format_structured


@dataclass
class Change:
    category: str
    original: str
    replacement: str
    rule: str


@dataclass
class CorrectionResult:
    raw: str
    text: str
    changes: List[Change] = field(default_factory=list)


# Build a flat, longest-first alias table once at import: alias(lower) ->
# (canonical, category, rule). Longest aliases first so multi-word phrases win.
def _build_alias_table() -> List[Tuple[str, str, str, str]]:
    table: List[Tuple[str, str, str, str]] = []
    for category, entries in TECH_ENTITIES.items():
        for canonical, aliases in entries:
            rule = f"{category}:{canonical}"
            # Only register the EXPLICIT alias phrases, never the canonical form
            # itself. Self-aliasing an ordinary word (e.g. "rest", "python")
            # would wrongly rewrite plain prose. Idempotency still holds because
            # the canonical output never matches one of its own aliases.
            seen = set()
            for alias in aliases:
                a = alias.lower()
                if a and a not in seen:
                    seen.add(a)
                    table.append((a, canonical, category, rule))
    for canonical, spellings in SPELLED_ACRONYMS.items():
        rule = f"acronym:{canonical}"
        # Only the spelled-out letter sequences, not the bare acronym word.
        for alias in spellings:
            table.append((alias.lower(), canonical, "acronym", rule))
    # Longest alias phrase first.
    table.sort(key=lambda t: len(t[0]), reverse=True)
    return table


_ALIAS_TABLE = _build_alias_table()

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "thirtieth": 30, "thirty first": 31,
    "thirty-first": 31,
}
_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
}


def _ordinal_suffix(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _parse_number_words(phrase: str) -> Optional[int]:
    """Parse a small compound cardinal number phrase ("ninety five") to int.

    Handles digits, single number words, and tens+ones compounds (21-99).
    Returns None if the phrase is not a clean number expression.
    """
    phrase = phrase.strip().lower()
    if not phrase:
        return None
    if phrase.isdigit():
        return int(phrase)
    tokens = phrase.split()
    if len(tokens) == 1:
        return _NUMBER_WORDS.get(tokens[0])
    if len(tokens) == 2:
        # "one hundred" / "two hundred" -> 100 / 200 (conservative, exact).
        if tokens[1] == "hundred":
            base = _NUMBER_WORDS.get(tokens[0])
            if base is not None and 1 <= base <= 9:
                return base * 100
        tens = _NUMBER_WORDS.get(tokens[0])
        ones = _NUMBER_WORDS.get(tokens[1])
        if tens is not None and ones is not None and tens % 10 == 0 and 1 <= ones <= 9:
            return tens + ones
    return None


class TechnicalCorrector:
    def __init__(
        self,
        enable_technical: bool = True,
        enable_formatting: bool = True,
        user_vocabulary: Optional[List[Tuple[str, str]]] = None,
        enable_structured: bool = True,
    ):
        self._enable_technical = enable_technical
        self._enable_formatting = enable_formatting
        self._user_vocab = user_vocabulary or []
        # Phase 6I context-aware structured formatting (URL/path/email/vN). It
        # is part of the "structured formatting" feature and is gated by
        # enable_formatting; this extra flag lets callers (benchmark, tests)
        # isolate the Phase 6I contribution from the Phase 6G number/date rules.
        self._enable_structured = enable_structured

    # --- public API -----------------------------------------------------
    def normalize(self, text: str) -> CorrectionResult:
        result = CorrectionResult(raw=text, text=text)
        if not text or not text.strip():
            result.text = text
            return result

        # 1) Whitespace normalization (collapse runs of spaces/tabs; keep
        #    newlines). Does not touch punctuation.
        new = self._normalize_whitespace(result.text)
        result.text = new

        # 2) Technical aliases + spelled acronyms (registered, word-boundary).
        if self._enable_technical:
            result.text = self._apply_aliases(result.text, result.changes)

        # 3) Conservative structured formatting.
        if self._enable_formatting:
            result.text = self._apply_formatting(result.text, result.changes)

        # 4) Explicit user vocabulary (last; user-controlled).
        if self._user_vocab:
            result.text = self._apply_user_vocab(result.text, result.changes)

        return result

    # --- stages ---------------------------------------------------------
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        # Collapse spaces/tabs but preserve newlines; strip trailing spaces.
        lines = text.split("\n")
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in lines]
        return "\n".join(lines)

    def _apply_aliases(self, text: str, changes: List[Change]) -> str:
        for alias, canonical, category, rule in _ALIAS_TABLE:
            # Whole-phrase, case-insensitive, word-boundary match. Allow the
            # internal spaces of the alias to match one-or-more spaces.
            pattern = r"\b" + r"\s+".join(re.escape(w) for w in alias.split()) + r"\b"

            def _repl(m, canon=canonical, cat=category, r=rule):
                matched = m.group(0)
                if matched != canon:  # only record a real change
                    changes.append(
                        Change(category=cat, original=matched, replacement=canon,
                               rule=r)
                    )
                return canon

            text = re.sub(pattern, _repl, text, flags=re.IGNORECASE)
        return text

    def _apply_formatting(self, text: str, changes: List[Change]) -> str:
        # Phase 6I: context-aware structured expressions (URL/path/email/vN)
        # run FIRST, consuming the spoken word "dot"/"slash"/"at" only inside a
        # strongly-anchored structure. They never touch the word "point", so the
        # Phase 6G number formatter below is unaffected.
        if self._enable_structured:
            text = self._apply_structured(text, changes)
        text = self._format_percent(text, changes)
        text = self._format_decimal_version(text, changes)
        text = self._format_dates(text, changes)
        return text

    def _apply_structured(self, text: str, changes: List[Change]) -> str:
        matches = format_structured(text)
        if not matches:
            return text
        # Apply right-to-left so earlier char offsets stay valid.
        for cstart, cend, original, replacement, rule in sorted(
            matches, key=lambda m: m[0], reverse=True
        ):
            text = text[:cstart] + replacement + text[cend:]
            changes.append(
                Change(category="structured", original=original,
                       replacement=replacement, rule=rule)
            )
        return text

    def _format_percent(self, text: str, changes: List[Change]) -> str:
        # "<number phrase> percent" -> "N%". The number phrase is digits or up
        # to a two-word cardinal ("ninety five"). Only converts clean numbers.
        def repl(m):
            n = _parse_number_words(m.group("num"))
            if n is None:
                return m.group(0)
            changes.append(Change("number", m.group(0), f"{n}%", "percent"))
            return f"{n}%"

        return re.sub(
            r"\b(?P<num>\d+|[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+percent\b", repl, text
        )

    def _format_decimal_version(self, text: str, changes: List[Change]) -> str:
        # "<int> point <int>" -> "X.Y" where both sides are digits or
        # number-words. Conservative: only single "point" between two numbers.
        def to_int(tok):
            if tok.isdigit():
                return tok
            n = _NUMBER_WORDS.get(tok.lower())
            return str(n) if n is not None else None

        def repl(m):
            a, b = to_int(m.group("a")), to_int(m.group("b"))
            if a is None or b is None:
                return m.group(0)
            out = f"{a}.{b}"
            changes.append(Change("number", m.group(0), out, "decimal_version"))
            return out

        return re.sub(
            r"\b(?P<a>\d+|[A-Za-z]+)\s+point\s+(?P<b>\d+|[A-Za-z]+)\b", repl, text
        )

    def _format_dates(self, text: str, changes: List[Change]) -> str:
        # "<Month> <ordinal-word>" -> "<Month> Nth". Only recognized months +
        # ordinal words.
        def repl(m):
            month = m.group("month").capitalize()
            ordw = m.group("ord").lower()
            n = _ORDINAL_WORDS.get(ordw)
            if n is None:
                return m.group(0)
            out = f"{month} {n}{_ordinal_suffix(n)}"
            changes.append(Change("date", m.group(0), out, "month_ordinal"))
            return out

        month_alt = "|".join(sorted(_MONTHS, key=len, reverse=True))
        ord_alt = "|".join(
            sorted((re.escape(o) for o in _ORDINAL_WORDS), key=len, reverse=True)
        )
        pattern = rf"\b(?P<month>{month_alt})\s+(?P<ord>{ord_alt})\b"
        return re.sub(pattern, repl, text, flags=re.IGNORECASE)

    def _apply_user_vocab(self, text: str, changes: List[Change]) -> str:
        for original, replacement in self._user_vocab:
            if not original:
                continue
            pattern = r"\b" + re.escape(original) + r"\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                changes.append(
                    Change("user", original, replacement, "user_vocabulary")
                )
        return text


def correct_transcript(
    text: str,
    enable_technical: bool = True,
    enable_formatting: bool = True,
    user_vocabulary: Optional[List[Tuple[str, str]]] = None,
    enable_structured: bool = True,
) -> CorrectionResult:
    """Convenience wrapper returning the explainable CorrectionResult."""
    return TechnicalCorrector(
        enable_technical=enable_technical,
        enable_formatting=enable_formatting,
        user_vocabulary=user_vocabulary,
        enable_structured=enable_structured,
    ).normalize(text)
