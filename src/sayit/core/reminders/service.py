"""Bridge: conversational task proposals -> real persistent reminders.

This is the ONE authoritative execution path shared by typed and spoken input
(both arrive as a confirmed ``TaskProposal`` from the ConversationEngine). It
reuses the existing ``ActionCoordinator`` guards (confirmation, stale-revision
rejection, idempotency) so:

* a proposal only becomes a reminder after explicit confirmation AND successful
  persistence (never "optimistically");
* a stale confirmation (the proposal changed after confirm was requested) is
  rejected and the user is asked to re-confirm the latest revision;
* repeated confirmation / retry never creates a duplicate reminder (idempotency
  key = the proposal id);
* casual mentions ("I have a meeting tomorrow") are NOT auto-scheduled — only
  an explicit reminder intent with a resolved date is eligible.

It also maps conversational corrections (reschedule / retitle / cancel / snooze)
onto the REAL scheduled reminder record, and answers simple queries. It never
performs shell/filesystem actions and needs no cloud/LLM.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import List, Optional

from ..conversation.safe_action import ActionCoordinator, ActionError
from ..conversation.state import SlotName, TaskProposal, TaskStatus
from .model import Reminder, ReminderError, ReminderStatus, build_trigger
from .store import ReminderStore


@dataclass
class ScheduleResult:
    ok: bool
    reminder: Optional[Reminder] = None
    message: str = ""
    needs_confirmation: bool = False
    stale: bool = False
    duplicate: bool = False


# Required slots for a schedulable reminder: a goal that is a reminder-ish
# intent AND a resolved date. Time is optional (defaults applied).
_REMINDER_GOALS = {"reminder", "meeting", "event", "appointment"}


class ReminderService:
    def __init__(
        self,
        store: ReminderStore,
        *,
        local_tz: Optional[_dt.tzinfo] = None,
        default_time: str = "09:00",
    ):
        self._store = store
        self._coord = ActionCoordinator()
        self._tz = local_tz or _dt.datetime.now().astimezone().tzinfo or _dt.timezone.utc
        self._default_time = default_time
        # Links a conversation proposal id -> the reminder id it created, so a
        # correction on the proposal updates the right scheduled record.
        self._proposal_to_reminder: dict[str, str] = {}

    @property
    def store(self) -> ReminderStore:
        return self._store

    # -- eligibility -----------------------------------------------------
    def is_schedulable(self, task: TaskProposal) -> bool:
        """True only for an EXPLICIT reminder request with a resolved date.

        A general statement about a meeting (no reminder/schedule intent, or no
        concrete date) is NOT schedulable — we never auto-create reminders from
        casual conversation.
        """
        if task is None:
            return False
        goal = task.get(SlotName.GOAL)
        if goal not in _REMINDER_GOALS:
            return False
        return bool(task.get(SlotName.DATE))

    def _title_for(self, task: TaskProposal) -> str:
        subject = task.get(SlotName.SUBJECT)
        goal = task.get(SlotName.GOAL) or "reminder"
        if subject and subject.strip():
            return self._clean_title(subject)
        return goal.capitalize()

    @staticmethod
    def _clean_title(raw: str) -> str:
        """Tidy an auto-extracted subject into a readable title.

        Collapses repeated whitespace and strips dangling trailing prepositions
        ("project meeting  at" -> "project meeting") left by the shared slot
        extractor. Does NOT alter the extractor itself (shared with dictation).
        """
        import re

        t = re.sub(r"\s+", " ", (raw or "").strip())
        t = re.sub(r"\s+\b(?:at|on|for|about|to|the|a|an)\b\s*$", "", t, flags=re.IGNORECASE).strip()
        return t or "Reminder"

    # -- confirmation + execution (safe, idempotent) --------------------
    def request_confirmation(self, task: TaskProposal) -> ScheduleResult:
        """Move an eligible DRAFT to AWAITING_CONFIRM. Does not schedule yet."""
        if not self.is_schedulable(task):
            return ScheduleResult(
                ok=False,
                message="That isn't a complete reminder yet — I need at least a "
                        "date (e.g. 'remind me about X tomorrow at 10am').",
            )
        ready = self._coord.request_confirmation(
            task, required=[SlotName.GOAL.value, SlotName.DATE.value]
        )
        if not ready:
            return ScheduleResult(ok=False, message="Missing required details.")
        trigger = self._safe_trigger(task)
        when = trigger.strftime("%A %b %d at %I:%M %p").replace(" 0", " ")
        return ScheduleResult(
            ok=True, needs_confirmation=True,
            message=f"Schedule a reminder '{self._title_for(task)}' for {when}? "
                    f"(revision {task.revision_number})",
        )

    def confirm_and_schedule(
        self, task: TaskProposal, *, expected_revision: int
    ) -> ScheduleResult:
        """Create ONE persistent reminder after explicit confirmation.

        Guards via ActionCoordinator: stale-revision rejection + idempotency.
        The proposal is marked EXECUTED only AFTER persistence succeeds.
        """
        if not self.is_schedulable(task):
            return ScheduleResult(ok=False, message="Not a schedulable reminder.")

        # Build the trigger up-front so a bad date fails BEFORE we touch state.
        try:
            trigger = self._safe_trigger(task)
        except ReminderError as e:
            return ScheduleResult(ok=False, message=str(e))

        # Idempotency: if this proposal already created a reminder, return it.
        existing = self._store.find_by_idempotency_key(task.id)
        if existing is not None:
            task_already = task.status is TaskStatus.EXECUTED
            return ScheduleResult(
                ok=True, reminder=existing, duplicate=True,
                message=f"Already scheduled '{existing.title}'.",
            )

        created: dict = {}

        def _capability(t: TaskProposal) -> str:
            reminder = Reminder(
                title=self._title_for(t),
                trigger_at=trigger,
                description="",
                idempotency_key=t.id,
            )
            stored = self._store.add(reminder)  # persists; idempotent
            created["reminder"] = stored
            self._proposal_to_reminder[t.id] = stored.id
            return stored.id  # effect id

        try:
            result = self._coord.execute(
                task, _capability,
                expected_revision=expected_revision, confirmed=True,
            )
        except ActionError as e:
            # Stale revision (correction landed after confirm) -> re-confirm.
            return ScheduleResult(
                ok=False, stale=True,
                needs_confirmation=True,
                message=f"{e} Please confirm the updated reminder.",
            )

        if not result.ok:
            return ScheduleResult(ok=False, message=result.message)
        reminder = created.get("reminder") or self._store.get(result.effect_id)
        when = reminder.trigger_at.strftime("%A %b %d at %I:%M %p").replace(" 0", " ")
        return ScheduleResult(
            ok=True, reminder=reminder, duplicate=result.duplicate_suppressed,
            message=f"Scheduled '{reminder.title}' for {when}.",
        )

    def _safe_trigger(self, task: TaskProposal) -> _dt.datetime:
        return build_trigger(
            task.get(SlotName.DATE),
            task.get(SlotName.TIME),
            tz=self._tz,
            now=self._store.now(),
            default_time=self._default_time,
        )

    # -- corrections on REAL reminders ----------------------------------
    def reminder_for_proposal(self, proposal_id: str) -> Optional[Reminder]:
        rid = self._proposal_to_reminder.get(proposal_id)
        return self._store.get(rid) if rid else None

    def reschedule(
        self, reminder_id: str, *, date_iso: Optional[str], time_24h: Optional[str],
        source_text: str = "",
    ) -> ScheduleResult:
        r = self._store.get(reminder_id)
        if r is None:
            return ScheduleResult(ok=False, message="No such reminder.")
        if r.status in (ReminderStatus.COMPLETED, ReminderStatus.CANCELLED):
            return ScheduleResult(
                ok=False,
                message=f"That reminder is {r.status.value}; I can't reschedule it. "
                        "Create a new one instead.",
            )
        # Keep unaffected component: reuse existing local date/time when only one
        # part is being changed.
        local = r.trigger_at.astimezone(self._tz)
        new_date = date_iso or local.date().isoformat()
        new_time = time_24h or local.strftime("%H:%M")
        try:
            trigger = build_trigger(
                new_date, new_time, tz=self._tz, now=self._store.now(),
                default_time=self._default_time,
            )
        except ReminderError as e:
            return ScheduleResult(ok=False, message=str(e))
        r.reschedule(trigger, source_text=source_text)
        self._store.update(r)
        when = trigger.strftime("%A %b %d at %I:%M %p").replace(" 0", " ")
        return ScheduleResult(ok=True, reminder=r, message=f"Moved '{r.title}' to {when}.")

    def retitle(self, reminder_id: str, new_title: str, *, source_text: str = "") -> ScheduleResult:
        r = self._store.get(reminder_id)
        if r is None:
            return ScheduleResult(ok=False, message="No such reminder.")
        if r.status in (ReminderStatus.COMPLETED, ReminderStatus.CANCELLED):
            return ScheduleResult(ok=False, message=f"That reminder is {r.status.value}.")
        try:
            r.retitle(new_title, source_text=source_text)
        except ReminderError as e:
            return ScheduleResult(ok=False, message=str(e))
        self._store.update(r)
        return ScheduleResult(ok=True, reminder=r, message=f"Renamed to '{r.title}'.")

    def cancel(self, reminder_id: str, *, source_text: str = "") -> ScheduleResult:
        r = self._store.get(reminder_id)
        if r is None:
            return ScheduleResult(ok=False, message="No such reminder.")
        if r.status is ReminderStatus.COMPLETED:
            return ScheduleResult(ok=False, message="That reminder is already completed.")
        if r.status is ReminderStatus.NOTIFIED:
            # Already fired: cancelling future delivery is a no-op but honest.
            return ScheduleResult(
                ok=False,
                message="That reminder already fired; I can't un-send a "
                        "notification. I can mark it complete instead.",
            )
        r.cancel(source_text=source_text)
        self._store.update(r)
        return ScheduleResult(ok=True, reminder=r, message=f"Cancelled '{r.title}'.")

    def complete(self, reminder_id: str, *, source_text: str = "") -> ScheduleResult:
        r = self._store.get(reminder_id)
        if r is None:
            return ScheduleResult(ok=False, message="No such reminder.")
        r.complete(source_text=source_text)
        self._store.update(r)
        return ScheduleResult(ok=True, reminder=r, message=f"Marked '{r.title}' complete.")

    def snooze(
        self, reminder_id: str, delta: _dt.timedelta, *, source_text: str = ""
    ) -> ScheduleResult:
        r = self._store.get(reminder_id)
        if r is None:
            return ScheduleResult(ok=False, message="No such reminder.")
        if r.status in (ReminderStatus.COMPLETED, ReminderStatus.CANCELLED):
            return ScheduleResult(ok=False, message=f"That reminder is {r.status.value}.")
        try:
            r.snooze(delta, now=self._store.now(), source_text=source_text)
        except ReminderError as e:
            return ScheduleResult(ok=False, message=str(e))
        self._store.update(r)
        when = r.trigger_at.astimezone(self._tz).strftime("%I:%M %p").replace(" 0", " ")
        return ScheduleResult(ok=True, reminder=r, message=f"Snoozed '{r.title}' until {when}.")

    # -- queries ---------------------------------------------------------
    def query_on_date(self, day: _dt.date) -> List[Reminder]:
        return self._store.on_date(day, self._tz)

    def upcoming(self) -> List[Reminder]:
        return self._store.upcoming()
