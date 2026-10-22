"""Durable, local reminder storage.

Persists reminders to ``reminders.json`` in the SayIt data dir — SEPARATE from
conversation history (``conversation.json``) and notes (``notes.json``). This is
deliberate: disabling optional chat-history retention must NEVER delete real
reminders. There is no network, no telemetry, no cloud sync, and no database
dependency — a single atomically-written JSON file.

Robustness mirrors NotesStore: atomic temp-file + ``os.replace`` writes, and a
malformed/partial file loads as an empty store (with a ``.corrupt.bak`` backup)
rather than crashing.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .model import Reminder, ReminderStatus


def _default_path() -> Path:
    from ..settings.settings import get_data_dir

    return get_data_dir() / "reminders.json"


def _default_clock() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class ReminderStore:
    """Load/save reminders with atomic persistence and an injected clock."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        path: Optional[Path] = None,
        clock: Optional[Callable[[], _dt.datetime]] = None,
    ):
        self._path = Path(path) if path else _default_path()
        self._clock = clock or _default_clock
        self._reminders: Dict[str, Reminder] = {}
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def now(self) -> _dt.datetime:
        """Current instant from the injected clock (timezone-aware)."""
        t = self._clock()
        if t.tzinfo is None:
            return t.replace(tzinfo=_dt.timezone.utc)
        return t

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        self._reminders = {}
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("reminders", []):
                try:
                    r = Reminder.from_dict(item)
                    self._reminders[r.id] = r
                except Exception:
                    continue  # skip a single malformed reminder, keep the rest
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # Corrupt/unreadable: back it up and start clean (never crash, never
            # silently destroy — a recovery copy is kept).
            try:
                os.replace(self._path, self._path.with_suffix(".corrupt.bak"))
            except OSError:
                pass
            self._reminders = {}

    def save(self) -> None:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "reminders": [r.to_dict() for r in self._reminders.values()],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".reminders-", suffix=".tmp"
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

    # -- CRUD ------------------------------------------------------------
    def add(self, reminder: Reminder) -> Reminder:
        """Add a reminder idempotently.

        If a reminder with the same ``idempotency_key`` already exists, the
        EXISTING reminder is returned and nothing new is created — so a repeated
        confirmation/retry can never duplicate a scheduled reminder.
        """
        if reminder.idempotency_key:
            existing = self.find_by_idempotency_key(reminder.idempotency_key)
            if existing is not None:
                return existing
        self._reminders[reminder.id] = reminder
        self.save()
        return reminder

    def update(self, reminder: Reminder) -> None:
        self._reminders[reminder.id] = reminder
        self.save()

    def get(self, reminder_id: str) -> Optional[Reminder]:
        return self._reminders.get(reminder_id)

    def find_by_idempotency_key(self, key: str) -> Optional[Reminder]:
        for r in self._reminders.values():
            if r.idempotency_key and r.idempotency_key == key:
                return r
        return None

    def remove(self, reminder_id: str) -> bool:
        if reminder_id in self._reminders:
            del self._reminders[reminder_id]
            self.save()
            return True
        return False

    # -- queries ---------------------------------------------------------
    def all(self) -> List[Reminder]:
        return sorted(self._reminders.values(), key=lambda r: r.trigger_utc())

    def active(self) -> List[Reminder]:
        return [r for r in self.all() if r.is_active()]

    def due(self, now: Optional[_dt.datetime] = None) -> List[Reminder]:
        now = now or self.now()
        return [r for r in self.all() if r.is_due(now)]

    def upcoming(self, now: Optional[_dt.datetime] = None) -> List[Reminder]:
        now = now or self.now()
        now_utc = now.astimezone(_dt.timezone.utc)
        return [r for r in self.active() if r.trigger_utc() > now_utc]

    def on_date(self, day: _dt.date, tz: _dt.tzinfo) -> List[Reminder]:
        """Active reminders whose LOCAL (tz) date equals ``day``."""
        out = []
        for r in self.active():
            local = r.trigger_at.astimezone(tz)
            if local.date() == day:
                out.append(r)
        return out

    def count(self) -> int:
        return len(self._reminders)
