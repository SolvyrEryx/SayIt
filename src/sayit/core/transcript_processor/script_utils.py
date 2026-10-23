"""Script detection helpers for script-safe transcript correction.

The on-device technical-correction layer is English/Latin-oriented: its alias
table, acronym expansion, number/date/structured formatting are all defined for
Latin-script English. Running those rules on Devanagari (Hindi) or Kannada
output risks corrupting correct native-script transcripts.

These helpers let the pipeline *abstain* (leave text untouched) when a
transcript is predominantly non-Latin. Detection is deterministic, local, and
based only on Unicode code-point ranges — no model, network, or logging.
"""

from __future__ import annotations

# Unicode blocks for the scripts we explicitly support in dictation.
_DEVANAGARI = (0x0900, 0x097F)
_KANNADA = (0x0C80, 0x0CFF)

# Broader "Indic / complex script" net used for the abstain decision. If a
# transcript is mostly characters from these blocks, Latin-oriented correction
# rules should not run.
_NON_LATIN_BLOCKS = (
    (0x0900, 0x097F),  # Devanagari
    (0x0980, 0x09FF),  # Bengali/Assamese
    (0x0A00, 0x0A7F),  # Gurmukhi
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Oriya
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
    (0x0600, 0x06FF),  # Arabic (Urdu/Kashmiri)
)


def _in_block(cp: int, block: tuple[int, int]) -> bool:
    return block[0] <= cp <= block[1]


def contains_devanagari(text: str) -> bool:
    return any(_in_block(ord(c), _DEVANAGARI) for c in text)


def contains_kannada(text: str) -> bool:
    return any(_in_block(ord(c), _KANNADA) for c in text)


def non_latin_ratio(text: str) -> float:
    """Fraction of *letters* that fall in a supported non-Latin block.

    Whitespace, digits, and punctuation are ignored so that, e.g., a Hindi
    sentence with an embedded ASCII number is still recognised as non-Latin.
    Returns 0.0 for empty/letterless input.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    non_latin = 0
    for c in letters:
        cp = ord(c)
        if any(_in_block(cp, b) for b in _NON_LATIN_BLOCKS):
            non_latin += 1
    return non_latin / len(letters)


def is_predominantly_non_latin(text: str, threshold: float = 0.2) -> bool:
    """True if enough of the text is non-Latin that Latin-oriented correction
    should abstain. The threshold is intentionally low (0.2): even partial
    native-script content means the English rules are unsafe to apply.
    """
    return non_latin_ratio(text) >= threshold
