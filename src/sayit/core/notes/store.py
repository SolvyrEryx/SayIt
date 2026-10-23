"""Local, on-device notes storage with autosave + restart persistence.

A deliberately small, dependency-free store for the standalone Notes panel. It
persists to a single JSON file in the SayIt data directory (same place as other
local user data) so notes survive restarts. There is no network, no telemetry,
and no cloud sync — notes never leave the machine.

Design:
* One active note at a time (the panel edits the active note). Multiple notes
  are supported for forward-compatibility but the v0.2.0 panel uses a single
  default note.
* ``set_active_content`` updates the in-memory active note and marks it dirty.
* ``save`` writes atomically (temp file + os.replace) so a crash mid-write
  never corrupts the store. ``autosave`` only writes when dirty.
* All writes are debounced by the caller (the panel), not here; this class is
  pure state + durable persistence and is fully unit-testable without Qt.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def _default_notes_path() -> Path:
    # Lazy import so tests can monkeypatch the data dir via settings.
    from ..settings.settings import get_data_dir

    return get_data_dir() / "notes.json"


@dataclass
class Note:
    id: str
    title: str = "Note"
    content: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            id=str(data.get("id", "default")),
            title=str(data.get("title", "Note")),
            content=str(data.get("content", "")),
            updated_at=float(data.get("updated_at", time.time())),
        )


_DEFAULT_ID = "default"


class NotesStore:
    """Durable, local notes store. Single active note for the v0.2.0 panel."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path else _default_notes_path()
        self._notes: Dict[str, Note] = {}
        self._active_id: str = _DEFAULT_ID
        self._dirty = False
        self.load()

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        self._notes = {}
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("notes", []):
                    note = Note.from_dict(item)
                    self._notes[note.id] = note
                active = data.get("active_id")
                if active in self._notes:
                    self._active_id = active
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                # Corrupt/unreadable store: start clean rather than crash. A
                # best-effort backup is kept so nothing is silently destroyed.
                try:
                    bak = self._path.with_suffix(".corrupt.bak")
                    os.replace(self._path, bak)
                except OSError:
                    pass
                self._notes = {}
        if _DEFAULT_ID not in self._notes:
            self._notes[_DEFAULT_ID] = Note(id=_DEFAULT_ID)
            self._active_id = _DEFAULT_ID
        self._dirty = False

    def save(self) -> None:
        """Atomically persist the store. Always writes (ignores dirty flag)."""
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "active_id": self._active_id,
            "notes": [n.to_dict() for n in self._notes.values()],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp file in same dir, then replace.
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".notes-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self._dirty = False

    def autosave(self) -> bool:
        """Persist only if there are unsaved changes. Returns True if written."""
        if self._dirty:
            self.save()
            return True
        return False

    # -- active note accessors ------------------------------------------
    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def path(self) -> Path:
        return self._path

    def active_note(self) -> Note:
        return self._notes[self._active_id]

    def get_active_content(self) -> str:
        return self.active_note().content

    def set_active_content(self, content: str) -> None:
        note = self.active_note()
        if note.content != content:
            note.content = content
            note.updated_at = time.time()
            self._dirty = True

    def append_to_active(self, text: str, *, separator: str = " ") -> str:
        """Append dictated text to the active note and return the new content.

        If the note already has content and does not end in whitespace, a single
        separator space is inserted so dictated fragments do not run together.
        """
        note = self.active_note()
        current = note.content
        if current and not current[-1].isspace() and text and not text[0].isspace():
            new_content = current + separator + text
        else:
            new_content = current + text
        note.content = new_content
        note.updated_at = time.time()
        self._dirty = True
        return new_content

    def list_notes(self) -> List[Note]:
        return list(self._notes.values())

    # -- multiple notes (create / select) --------------------------------
    def _new_note_id(self) -> str:
        """A short, collision-free note id."""
        import uuid

        while True:
            candidate = uuid.uuid4().hex[:12]
            if candidate not in self._notes:
                return candidate

    def create_note(self, *, title: str = "", content: str = "") -> Note:
        """Create a new note, make it active, and return it.

        Deterministic defaults: an empty title normalizes to "Note" and the body
        defaults to empty. Creating a note does NOT touch any other note (the
        current note and its edits are preserved by the caller flushing first).
        The store is marked dirty so the new note persists on the next save.
        """
        note = Note(id=self._new_note_id(), title=(title.strip() or "Note"), content=content)
        self._notes[note.id] = note
        self._active_id = note.id
        self._dirty = True
        return note

    def select_note(self, note_id: str) -> bool:
        """Switch the active note. Returns False if the id is unknown.

        Switching is non-destructive: it never mutates note contents. Marks the
        store dirty so the active-note selection is persisted.
        """
        if note_id not in self._notes:
            return False
        if note_id != self._active_id:
            self._active_id = note_id
            self._dirty = True
        return True

    def get_note(self, note_id: str) -> Optional[Note]:
        return self._notes.get(note_id)

    def count(self) -> int:
        return len(self._notes)
