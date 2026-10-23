"""Privacy-aware persistence for assistant conversations.

Default is IN-MEMORY: nothing is written to disk unless the user has explicitly
enabled conversation retention (``enabled``). Even when enabled, the serialized
form (ConversationState.to_dict) excludes API keys/auth and normalizes away any
executed/pending action status so a restored conversation can never replay an
external side effect.

Atomic writes (temp + os.replace); malformed/partial files load as an empty
in-memory conversation rather than crashing, and a best-effort backup of the
corrupt file is kept.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from .state import ConversationState


def _default_path() -> Path:
    from ..settings.settings import get_data_dir

    return get_data_dir() / "conversation.json"


class ConversationStore:
    """Load/save a ConversationState, gated by an explicit retention opt-in."""

    SCHEMA_VERSION = 1

    def __init__(self, *, enabled: bool, path: Optional[Path] = None):
        self._enabled = bool(enabled)
        self._path = Path(path) if path else _default_path()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> ConversationState:
        """Return the stored conversation if retention is enabled, else empty.

        When disabled, this NEVER reads a prior file (no hidden second store).
        """
        if not self._enabled or not self._path.exists():
            return ConversationState()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ConversationState.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # Corrupt/unreadable: back it up and start clean (never crash).
            try:
                os.replace(self._path, self._path.with_suffix(".corrupt.bak"))
            except OSError:
                pass
            return ConversationState()

    def save(self, state: ConversationState) -> bool:
        """Persist ONLY when retention is enabled. Returns True if written."""
        if not self._enabled:
            return False
        payload = state.to_dict()
        payload["schema_version"] = self.SCHEMA_VERSION
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".conv-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return True

    def clear(self) -> None:
        """Remove all stored conversation data (clear-history)."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
