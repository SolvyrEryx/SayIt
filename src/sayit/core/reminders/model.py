"""Persistent reminder domain model.

A ``Reminder`` is a REAL scheduled item — distinct from a conversational
``TaskProposal`` (which is a draft being shaped in chat). A proposal becomes a
reminder only after explicit confirmation + successful persistence.

Design:
* Timezone-aware: the trigger time is stored as an ISO-8601 string WITH an
  explicit UTC offset so a saved reminder survives restarts and DST changes
  unambiguously. Comparisons are always done in UTC.
* Clock is injected (never ``datetime.now()`` hardcoded) so tests are
  deterministic and relative dates resolve against the configured local time.
* Revision tracking mirrors TaskProposal so corrections are auditable.
* An idempotency key protects against duplicate scheduling of the same effect.
* No credentials, no network, no Qt — pure data, fully unit-testable.
"""

from __future__ import annotations

import datetime as _dt
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReminderStatus(str, Enum):
    """Lifecycle of a persistent reminder."""

    PENDING = "pending"      # scheduled, not yet due
    NOTIFIED = "notified"    # fired a desktop notification (terminal-ish; dedupe)
    COMPLETED = "completed"  # user marked done
    DISMISSED = "dismissed"  # user dismissed the notification
    CANCELLED = "cancelled"  # user cancelled before firing
    SNOOZED = "snoozed"      # re-scheduled for a later trigger


# Statuses that still need the scheduler to watch them.
_ACTIVE = (ReminderStatus.PENDING, ReminderStatus.SNOOZED)
# Terminal statuses the scheduler never re-fires.
_TERMINAL = (
    ReminderStatus.NOTIFIED,
    ReminderStatus.COMPLETED,
    ReminderStatus.DISMISSED,
    ReminderStatus.CANCELLED,
)


class ReminderError(ValueError):
    """Raised for invalid reminder construction/scheduling requests."""


@dataclass
class ReminderRevision:
    index: int
    kind: str                 # "create" | "reschedule" | "retitle" | "snooze" | ...
    field: Optional[str]
    old_value: Any
    new_value: Any
    source_text: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "source_text": self.source_text,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReminderRevision":
        return cls(
            index=int(d["index"]),
            kind=str(d.get("kind", "")),
            field=d.get("field"),
            old_value=d.get("old_value"),
            new_value=d.get("new_value"),
            source_text=str(d.get("source_text", "")),
            timestamp=float(d.get("timestamp", time.time())),
        )


def _parse_aware(value: str) -> _dt.datetime:
    """Parse an ISO-8601 string into a timezone-AWARE datetime.

    A naive string (no offset) is rejected: a reminder must always carry an
    explicit timezone so restart/DST behavior is unambiguous.
    """
    dt = _dt.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ReminderError(f"trigger_at must be timezone-aware: {value!r}")
    return dt


@dataclass
class Reminder:
    """A single persistent, scheduled reminder."""

    title: str
    trigger_at: _dt.datetime  # MUST be timezone-aware
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    status: ReminderStatus = ReminderStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    revision_number: int = 0
    revisions: List[ReminderRevision] = field(default_factory=list)
    # Idempotency: the conversation proposal id (or effect id) that created this
    # reminder, so re-confirming the same proposal never creates a duplicate.
    idempotency_key: Optional[str] = None
    # Snooze bookkeeping: the ORIGINAL trigger before the latest snooze.
    original_trigger_at: Optional[_dt.datetime] = None
    # Set once a notification was actually delivered, for honest dedupe.
    notified_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ReminderError("Reminder title must be non-empty.")
        self.title = self.title.strip()
        if self.trigger_at.tzinfo is None:
            raise ReminderError("trigger_at must be timezone-aware.")

    # -- scheduling helpers ---------------------------------------------
    def trigger_utc(self) -> _dt.datetime:
        """The trigger instant normalized to UTC for comparisons."""
        return self.trigger_at.astimezone(_dt.timezone.utc)

    def is_active(self) -> bool:
        return self.status in _ACTIVE

    def is_due(self, now: _dt.datetime) -> bool:
        """True iff an ACTIVE reminder's trigger is at/after ``now`` (UTC-safe)."""
        if not self.is_active():
            return False
        now_utc = now.astimezone(_dt.timezone.utc) if now.tzinfo else now.replace(
            tzinfo=_dt.timezone.utc
        )
        return self.trigger_utc() <= now_utc

    def _record(self, kind: str, field_: Optional[str], old: Any, new: Any, src: str) -> None:
        self.revision_number += 1
        self.updated_at = time.time()
        self.revisions.append(
            ReminderRevision(
                index=self.revision_number, kind=kind, field=field_,
                old_value=old, new_value=new, source_text=src,
            )
        )

    # -- mutations (each records a revision) ----------------------------
    def reschedule(self, new_trigger: _dt.datetime, *, source_text: str = "") -> None:
        if new_trigger.tzinfo is None:
            raise ReminderError("new trigger must be timezone-aware.")
        if self.status in _TERMINAL and self.status is not ReminderStatus.NOTIFIED:
            raise ReminderError(
                f"Cannot reschedule a {self.status.value} reminder."
            )
        old = self.trigger_at.isoformat()
        self.trigger_at = new_trigger
        # Rescheduling re-activates a reminder so the scheduler watches it again.
        if self.status in (ReminderStatus.NOTIFIED, ReminderStatus.SNOOZED):
            self.status = ReminderStatus.PENDING
        self._record("reschedule", "trigger_at", old, new_trigger.isoformat(), source_text)

    def retitle(self, new_title: str, *, source_text: str = "") -> None:
        nt = (new_title or "").strip()
        if not nt:
            raise ReminderError("New title must be non-empty.")
        old = self.title
        self.title = nt
        self._record("retitle", "title", old, nt, source_text)

    def snooze(self, delta: _dt.timedelta, *, now: _dt.datetime, source_text: str = "") -> None:
        """Push the trigger to ``now + delta`` and mark SNOOZED (re-watched)."""
        if delta.total_seconds() <= 0:
            raise ReminderError("Snooze duration must be positive.")
        if self.original_trigger_at is None:
            self.original_trigger_at = self.trigger_at
        base = now.astimezone(self.trigger_at.tzinfo) if now.tzinfo else now
        old = self.trigger_at.isoformat()
        self.trigger_at = base + delta
        self.status = ReminderStatus.SNOOZED
        self.notified_at = None  # allow a fresh notification at the new time
        self._record("snooze", "trigger_at", old, self.trigger_at.isoformat(), source_text)

    def mark_notified(self, *, when: Optional[float] = None) -> None:
        if self.status in _TERMINAL and self.status is not ReminderStatus.NOTIFIED:
            return
        old = self.status.value
        self.status = ReminderStatus.NOTIFIED
        self.notified_at = when if when is not None else time.time()
        self._record("notified", "status", old, self.status.value, "")

    def complete(self, *, source_text: str = "") -> None:
        old = self.status.value
        self.status = ReminderStatus.COMPLETED
        self._record("complete", "status", old, self.status.value, source_text)

    def dismiss(self, *, source_text: str = "") -> None:
        old = self.status.value
        self.status = ReminderStatus.DISMISSED
        self._record("dismiss", "status", old, self.status.value, source_text)

    def cancel(self, *, source_text: str = "") -> None:
        old = self.status.value
        self.status = ReminderStatus.CANCELLED
        self._record("cancel", "status", old, self.status.value, source_text)

    # -- serialization (no credentials ever) ----------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "trigger_at": self.trigger_at.isoformat(),
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision_number": self.revision_number,
            "revisions": [r.to_dict() for r in self.revisions],
            "idempotency_key": self.idempotency_key,
            "original_trigger_at": (
                self.original_trigger_at.isoformat() if self.original_trigger_at else None
            ),
            "notified_at": self.notified_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Reminder":
        trigger = _parse_aware(str(d["trigger_at"]))
        try:
            status = ReminderStatus(d.get("status", "pending"))
        except ValueError:
            status = ReminderStatus.PENDING
        orig = d.get("original_trigger_at")
        rem = cls(
            title=str(d.get("title") or "Reminder"),
            trigger_at=trigger,
            id=str(d.get("id") or uuid.uuid4().hex[:12]),
            description=str(d.get("description", "")),
            status=status,
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
            revision_number=int(d.get("revision_number", 0)),
            idempotency_key=d.get("idempotency_key"),
            original_trigger_at=_parse_aware(orig) if orig else None,
            notified_at=d.get("notified_at"),
        )
        for rd in d.get("revisions") or []:
            try:
                rem.revisions.append(ReminderRevision.from_dict(rd))
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed revision
        return rem


def build_trigger(
    date_iso: str,
    time_24h: Optional[str],
    *,
    tz: _dt.tzinfo,
    now: _dt.datetime,
    default_time: str = "09:00",
    allow_past: bool = False,
) -> _dt.datetime:
    """Compose a timezone-aware trigger from a resolved ISO date + HH:MM time.

    - ``date_iso`` is ``YYYY-MM-DD`` (already resolved by the slot extractor
      against the injected clock — we never re-guess "today" here).
    - ``time_24h`` is ``HH:MM`` or None (then ``default_time`` is used).
    - ``now`` is the injected current instant; a trigger in the past raises
      unless ``allow_past`` is set (used by missed-reminder reconciliation).
    """
    try:
        d = _dt.date.fromisoformat(date_iso)
    except (ValueError, TypeError) as e:
        raise ReminderError(f"Invalid date: {date_iso!r}") from e
    hhmm = time_24h or default_time
    try:
        hh, mm = (int(x) for x in hhmm.split(":"))
        t = _dt.time(hour=hh, minute=mm)
    except (ValueError, TypeError) as e:
        raise ReminderError(f"Invalid time: {hhmm!r}") from e
    trigger = _dt.datetime.combine(d, t).replace(tzinfo=tz)
    now_aware = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    if not allow_past and trigger <= now_aware:
        raise ReminderError(
            f"Scheduled time {trigger.isoformat()} is in the past "
            f"(now {now_aware.isoformat()})."
        )
    return trigger
