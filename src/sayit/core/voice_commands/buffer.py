"""Bounded recent-output buffer for Phase 8B voice editing.

Stores only what is needed to edit the most recent SayIt output. This is NOT
transcript history: it holds a single most-recent editable unit (the last text
SayIt produced), is in-memory only, is never written to disk, and is
independent of the user's history/privacy setting. It is cleared on demand.

Keeping it to one unit (plus derived sentence boundaries computed on the fly)
bounds memory and makes the semantics of "that" / "the last sentence"
unambiguous: they refer to the single most recent output.
"""

from __future__ import annotations

import re
from typing import List, Optional


class OutputBuffer:
    """Holds the most recent inserted output for voice editing.

    Only the latest unit is retained. A new ``set_output`` replaces the prior
    one; there is no growing list.
    """

    def __init__(self) -> None:
        self._current: Optional[str] = None

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def has_output(self) -> bool:
        return bool(self._current and self._current.strip())

    def set_output(self, text: Optional[str]) -> None:
        """Record the most recent output. ``None``/empty clears the buffer."""
        if text and text.strip():
            self._current = text
        else:
            self._current = None

    def clear(self) -> None:
        self._current = None

    # --- derived views (computed, not stored) ---------------------------
    def sentences(self) -> List[str]:
        """Split the current output into sentences (deterministic).

        A sentence ends at . ! or ? followed by whitespace/end. Keeps the
        terminator with the sentence. Returns [] when there is no output.
        """
        if not self.has_output:
            return []
        text = self._current.strip()
        # Split while keeping terminators. Conservative: only ./!/? boundaries.
        parts = re.findall(r"[^.!?]*[.!?]+|\S[^.!?]*$", text)
        return [p.strip() for p in parts if p.strip()]

    def last_sentence(self) -> Optional[str]:
        s = self.sentences()
        return s[-1] if s else None
