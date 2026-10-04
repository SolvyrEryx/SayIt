"""Phase 8G Smart Structure / dictation commands.

Converts explicit spoken structure commands into text structure. Strongly
anchored so ordinary nouns never trigger: "He made a good point." and "The
project has a new line of code." are left untouched.

Supported (small, high-value grammar):
- "new paragraph"      -> paragraph break (\\n\\n)
- "new line"           -> line break (\\n)   [whole-utterance only]
- explicit ordinal lists: "first ... second ... third ..." as separate dictated
  items -> a numbered Markdown list, ONLY when the ordinals clearly lead items.

Explicit spoken punctuation (comma, period, etc.) is intentionally NOT handled
here to avoid duplicating Phase 6G/6I; this engine focuses on block structure.
"""

from .structure import StructureResult, detect_structure

__all__ = ["StructureResult", "detect_structure"]
