"""Bridge conversational turns to real reminder operations.

This is the SINGLE authoritative entry point that both typed and spoken chat
input flow through (the ChatPanel calls it after each turn / on confirm). It
reuses the existing deterministic slot extractor and the already-tested
``ReminderService``; it does NOT modify the ConversationEngine, orchestrator or
the generic correction detector, so Phase 8H and the conversation behaviour are
untouched.

Responsibilities:
* decide whether a turn is a reminder MANAGEMENT intent (reschedule / retitle /
  cancel / snooze / query) that targets an ALREADY-scheduled reminder, and if
  so apply it to the real record via the service;
* expose ``confirm_active`` so the ChatPanel's "Confirm reminder" button schedules
  the current proposal through the authoritative service (stale-revision +
  idempotency guards live in the service/ActionCoordinator).

It never performs shell/filesystem actions and needs no cloud/LLM.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import List, Optional

from ..conversation.slots import extract_slots
from ..conversation.state import SlotName, TaskProposal
from .service import ReminderService, ScheduleResult


@dataclass
class BridgeReply:
    text: str
    handled: bool = False           # True if the bridge consumed this turn
    needs_clarification: bool = False
    reminder_id: Optional[str] = None


# Management-intent cues (reminder-specific; distinct from proposal corrections).
_RESCHEDULE_RE = re.compile(
    r"\b(move|reschedule|push|change|shift|set)\b.*\b(reminder|it|that|this)\b",
    re.IGNORECASE,
)
_SNOOZE_RE = re.compile(r"\bsnooze\b", re.IGNORECASE)
_CANCEL_RE = re.compile(r"\bcancel\b.*\breminder\b|\bcancel that\b|\bcancel it\b", re.IGNORECASE)
_RETITLE_RE = re.compile(
    r"\b(rename|retitle)\b|\bchange\b.*\b(title|name)\b.*\bto\b|\bcall it\b", re.IGNORECASE
)
_QUERY_RE = re.compile(
    r"\bwhat\b.*\breminders?\b|\blist\b.*\breminders?\b|\bdo i have\b.*\breminders?\b"
    r"|\bany reminders?\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"\b(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days)\b", re.IGNORECASE
)


def _parse_duration(text: str) -> Optional[_dt.timedelta]:
    m = _DURATION_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("min"):
        return _dt.timedelta(minutes=n)
    if unit.startswith(("hour", "hr")):
        return _dt.timedelta(hours=n)
    if unit.startswith("day"):
        return _dt.timedelta(days=n)
    return None


class ReminderConversationBridge:
    def __init__(self, service: ReminderService, engine):
        self._service = service
        self._engine = engine  # ConversationEngine (for ``today`` + active task)

    # -- confirmation (from the Confirm button) -------------------------
    def active_proposal_schedulable(self) -> bool:
        task = self._engine.state.active_task()
        if task is None or not task.is_open():
            return False
        # Not already linked to a scheduled reminder.
        if self._service.reminder_for_proposal(task.id) is not None:
            return False
        return self._service.is_schedulable(task)

    def describe_active_proposal(self) -> Optional[str]:
        task = self._engine.state.active_task()
        if task is None or not self._service.is_schedulable(task):
            return None
        rc = self._service.request_confirmation(task)
        return rc.message if rc.needs_confirmation else rc.message

    def confirm_active(self) -> ScheduleResult:
        """Schedule the active proposal via the authoritative service.

        The ChatPanel calls this from the Confirm button. The proposal's CURRENT
        revision is submitted; the service rejects a stale revision and is
        idempotent, so repeated clicks never create duplicates.
        """
        task = self._engine.state.active_task()
        if task is None or not self._service.is_schedulable(task):
            return ScheduleResult(ok=False, message="There's no reminder to confirm yet.")
        # Ensure the proposal is awaiting-confirm, then execute at its current rev.
        self._service.request_confirmation(task)
        return self._service.confirm_and_schedule(
            task, expected_revision=task.revision_number
        )

    # -- natural-language management (after a turn) ---------------------
    def _linked_reminder_id(self) -> Optional[str]:
        """The reminder most recently created from the active proposal, if any."""
        task = self._engine.state.active_task()
        if task is not None:
            r = self._service.reminder_for_proposal(task.id)
            if r is not None:
                return r.id
        # Fall back to the single most-recent active reminder (recency), so
        # "cancel that reminder" works even without a live proposal link.
        active = self._service.store.active()
        if len(active) == 1:
            return active[0].id
        return None

    def handle_turn(self, text: str) -> BridgeReply:
        """Try to handle ``text`` as a reminder-management intent.

        Returns ``handled=False`` when the turn is not a reminder-management
        request (the caller then runs the ordinary conversation turn). Shared by
        typed and spoken input.
        """
        t = (text or "").strip()
        if not t:
            return BridgeReply("", handled=False)

        # QUERY: "what reminders do I have tomorrow?"
        if _QUERY_RE.search(t):
            return self._handle_query(t)

        # Resolve a scheduled-reminder target (linked to the active proposal, or
        # the single active reminder by recency). Management intents only apply
        # when such a REAL reminder exists.
        rid = self._linked_reminder_id()

        # Does the active proposal still need confirmation (open + schedulable)?
        # If so, a "change the title" is proposal-shaping, NOT reminder
        # management — let the ordinary turn handle it so the Confirm button
        # stays authoritative.
        active_task = self._engine.state.active_task()
        proposal_pending = (
            active_task is not None
            and active_task.is_open()
            and self._service.is_schedulable(active_task)
        )

        mentions_reminder = bool(re.search(r"\breminder\b", t, re.IGNORECASE))
        has_mgmt_verb = bool(
            _SNOOZE_RE.search(t)
            or _CANCEL_RE.search(t)
            or _RETITLE_RE.search(t)
            or _RESCHEDULE_RE.search(t)
        )

        # Management applies when: an explicit 'reminder' word is used, OR a
        # scheduled reminder exists and the proposal is no longer pending (so the
        # correction clearly targets the real reminder).
        is_mgmt = has_mgmt_verb and (
            mentions_reminder or (rid is not None and not proposal_pending)
        )
        if not is_mgmt:
            return BridgeReply("", handled=False)

        if rid is None:
            active = self._service.store.active()
            if len(active) > 1:
                return BridgeReply(
                    "You have more than one reminder — which one should I change?",
                    handled=True, needs_clarification=True,
                )
            return BridgeReply(
                "I don't have a scheduled reminder to change yet.", handled=True
            )

        if _SNOOZE_RE.search(t):
            delta = _parse_duration(t) or _dt.timedelta(minutes=10)
            res = self._service.snooze(rid, delta, source_text=t)
            return BridgeReply(res.message, handled=True, reminder_id=rid if res.ok else None)

        if _CANCEL_RE.search(t):
            res = self._service.cancel(rid, source_text=t)
            return BridgeReply(res.message, handled=True, reminder_id=rid if res.ok else None)

        if _RETITLE_RE.search(t):
            title = self._extract_title(t)
            if not title:
                return BridgeReply("What should the new title be?", handled=True,
                                   needs_clarification=True)
            res = self._service.retitle(rid, title, source_text=t)
            return BridgeReply(res.message, handled=True, reminder_id=rid if res.ok else None)

        # RESCHEDULE: extract a new date and/or time from the phrase.
        ex = extract_slots(t, self._engine._today)
        if not (ex.date_iso or ex.time_24h):
            return BridgeReply(
                "When should I move it to? Give me a day or time.",
                handled=True, needs_clarification=True,
            )
        res = self._service.reschedule(
            rid, date_iso=ex.date_iso, time_24h=ex.time_24h, source_text=t
        )
        return BridgeReply(res.message, handled=True, reminder_id=rid if res.ok else None)

    # -- helpers ---------------------------------------------------------
    def _extract_title(self, text: str) -> str:
        m = re.search(r"\b(?:to|it)\s+(.+)$", text, re.IGNORECASE)
        if not m:
            return ""
        raw = m.group(1).strip().strip("\"'").rstrip(".")
        return raw

    def _handle_query(self, text: str) -> BridgeReply:
        today = self._engine._today
        ex = extract_slots(text, today)
        if ex.date_iso:
            day = _dt.date.fromisoformat(ex.date_iso)
            found = self._service.query_on_date(day)
            label = ex.date_phrase or ex.date_iso
        else:
            found = self._service.upcoming()
            label = "upcoming"
        if not found:
            return BridgeReply(f"You have no {label} reminders.", handled=True)
        lines = []
        tz = getattr(self._service, "_tz", _dt.timezone.utc)
        for r in found:
            when = r.trigger_at.astimezone(tz).strftime("%a %b %d %I:%M %p").replace(" 0", " ")
            lines.append(f"• {r.title} — {when}")
        return BridgeReply(
            f"You have {len(found)} {label} reminder(s):\n" + "\n".join(lines),
            handled=True,
        )
