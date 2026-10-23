"""Semantic conversation state + task proposal model.

Deliberately separate from raw transcripts: the state captures the *meaning* of
the active task (goal, entities, date/time, params, constraints) plus a revision
history explaining how it got there. The latest valid revision is authoritative
for reasoning; older transcript turns are retained only for context/debugging.

All types are plain dataclasses — no Qt, no network — so the whole model is
cheap to construct and fully unit-testable.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SlotName(str, Enum):
    """The structured fields a task proposal can carry."""

    GOAL = "goal"            # e.g. "reminder", "email draft", "meeting"
    SUBJECT = "subject"      # e.g. "project meeting"
    DATE = "date"            # normalized ISO date string (YYYY-MM-DD) when resolved
    DATE_PHRASE = "date_phrase"  # the user's words ("tomorrow", "Friday")
    TIME = "time"            # normalized HH:MM (24h) when resolved
    TIME_PHRASE = "time_phrase"
    PARTICIPANTS = "participants"


class TaskStatus(str, Enum):
    """Lifecycle of a task proposal (safe-action architecture)."""

    DRAFT = "draft"                  # still being shaped in conversation
    AWAITING_CONFIRM = "awaiting_confirm"  # all required info present; needs user OK
    EXECUTED = "executed"            # an external side effect occurred
    CANCELLED = "cancelled"          # user cancelled before execution
    FAILED = "failed"                # execution attempted and failed


@dataclass
class Revision:
    """One change to the task state, for the audit trail / explainability."""

    index: int
    kind: str                 # "create" | "update" | "add" | "remove" | "cancel" | "undo"
    field: Optional[str]      # slot/requirement affected (None for whole-task ops)
    old_value: Any
    new_value: Any
    source_text: str          # the user utterance that caused this revision
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskProposal:
    """A structured, revisable proposal for a single conversational task.

    ``revision_number`` increments on every state change and is used by the
    safe-action layer so a stale async result (computed against an older
    revision) can never overwrite a newer one. ``idempotency_key`` identifies
    the external effect so a retry/correction cannot duplicate it.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    slots: Dict[str, Any] = field(default_factory=dict)
    # Free-form additive requirements (e.g. report sections).
    requirements: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.DRAFT
    revision_number: int = 0
    revisions: List[Revision] = field(default_factory=list)
    idempotency_key: Optional[str] = None
    # Set once an external effect occurs, so post-execution corrections are
    # handled honestly rather than "rewritten in history".
    executed_effect_id: Optional[str] = None

    # -- slot helpers ----------------------------------------------------
    def get(self, slot: SlotName, default: Any = None) -> Any:
        return self.slots.get(slot.value, default)

    def _record(self, kind: str, field_: Optional[str], old: Any, new: Any, src: str) -> None:
        self.revision_number += 1
        self.revisions.append(
            Revision(
                index=self.revision_number,
                kind=kind,
                field=field_,
                old_value=old,
                new_value=new,
                source_text=src,
            )
        )

    def set_slot(self, slot: SlotName, value: Any, *, source_text: str) -> None:
        old = self.slots.get(slot.value)
        kind = "create" if not self.slots else "update"
        self.slots[slot.value] = value
        self._record(kind, slot.value, old, value, source_text)

    def update_slots(self, updates: Dict[SlotName, Any], *, source_text: str) -> None:
        for slot, value in updates.items():
            self.set_slot(slot, value, source_text=source_text)

    def add_requirement(self, req: str, *, source_text: str) -> bool:
        norm = req.strip()
        if not norm or norm.lower() in (r.lower() for r in self.requirements):
            return False
        self.requirements.append(norm)
        self._record("add", "requirements", None, norm, source_text)
        return True

    def remove_requirement(self, req: str, *, source_text: str) -> bool:
        target = req.strip().lower()
        # Normalize common articles so "remove the budget" matches "budget".
        target_core = re.sub(r"^(the|a|an)\s+", "", target).strip()
        for existing in list(self.requirements):
            ex = existing.lower()
            if (
                ex == target
                or ex == target_core
                or target_core in ex
                or ex in target_core
            ):
                self.requirements.remove(existing)
                self._record("remove", "requirements", existing, None, source_text)
                return True
        return False

    def cancel(self, *, source_text: str) -> None:
        old = self.status
        self.status = TaskStatus.CANCELLED
        self._record("cancel", "status", old.value, self.status.value, source_text)

    def mark_executed(self, effect_id: str) -> None:
        self.executed_effect_id = effect_id
        old = self.status
        self.status = TaskStatus.EXECUTED
        self._record("execute", "status", old.value, self.status.value, effect_id)

    # -- effective state -------------------------------------------------
    def effective(self) -> Dict[str, Any]:
        """The current authoritative view (latest valid revision of each slot)."""
        return {
            "id": self.id,
            "status": self.status.value,
            "revision": self.revision_number,
            "slots": dict(self.slots),
            "requirements": list(self.requirements),
        }

    def is_open(self) -> bool:
        """True while the task can still be shaped (not terminal)."""
        return self.status in (TaskStatus.DRAFT, TaskStatus.AWAITING_CONFIRM)

    # -- privacy-aware serialization ------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for optional persistence.

        Deliberately drops execution side-effect identity so a restored task can
        NEVER replay or duplicate an external effect: an executed task is stored
        as a plain record with status normalized away from EXECUTED and the
        effect id removed. Idempotency keys are not persisted either.
        """
        status = self.status
        if status in (TaskStatus.EXECUTED, TaskStatus.AWAITING_CONFIRM):
            # Do not persist a pending/executed action status that could drive a
            # post-restart side effect; restore as an inert draft record.
            persisted_status = TaskStatus.DRAFT.value
        else:
            persisted_status = status.value
        return {
            "id": self.id,
            "slots": dict(self.slots),
            "requirements": list(self.requirements),
            "status": persisted_status,
            "revision_number": self.revision_number,
            # Audit trail is kept for explanation, but without any effect ids.
            "revisions": [
                {
                    "index": r.index,
                    "kind": r.kind,
                    "field": r.field,
                    "old_value": r.old_value,
                    "new_value": r.new_value,
                    "source_text": r.source_text,
                }
                for r in self.revisions
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProposal":
        task = cls(
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            slots=dict(data.get("slots") or {}),
            requirements=list(data.get("requirements") or []),
            revision_number=int(data.get("revision_number") or 0),
        )
        try:
            task.status = TaskStatus(data.get("status", "draft"))
        except ValueError:
            task.status = TaskStatus.DRAFT
        # Never restore EXECUTED/effect state (defensive even if present).
        if task.status is TaskStatus.EXECUTED:
            task.status = TaskStatus.DRAFT
        task.executed_effect_id = None
        task.idempotency_key = None
        for rd in data.get("revisions") or []:
            try:
                task.revisions.append(
                    Revision(
                        index=int(rd["index"]),
                        kind=str(rd["kind"]),
                        field=rd.get("field"),
                        old_value=rd.get("old_value"),
                        new_value=rd.get("new_value"),
                        source_text=str(rd.get("source_text", "")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed revision entries
        return task


@dataclass
class ConversationState:
    """Multi-turn conversation: transcript turns + the active/known tasks.

    Only the LATEST valid revision of the active task is authoritative; the
    transcript list is bounded context for interpretation and is never blindly
    concatenated into provider requests.
    """

    turns: List[Dict[str, str]] = field(default_factory=list)  # {role, text}
    tasks: List[TaskProposal] = field(default_factory=list)
    active_task_id: Optional[str] = None
    max_turns: int = 40

    def add_turn(self, role: str, text: str) -> None:
        self.turns.append({"role": role, "text": text})
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def active_task(self) -> Optional[TaskProposal]:
        if self.active_task_id is None:
            return None
        for t in self.tasks:
            if t.id == self.active_task_id:
                return t
        return None

    def open_tasks(self) -> List[TaskProposal]:
        return [t for t in self.tasks if t.is_open()]

    def new_task(self) -> TaskProposal:
        task = TaskProposal()
        self.tasks.append(task)
        self.active_task_id = task.id
        return task

    def get_task(self, task_id: str) -> Optional[TaskProposal]:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    # -- privacy-aware serialization ------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "turns": [dict(t) for t in self.turns][-self.max_turns:],
            "tasks": [t.to_dict() for t in self.tasks],
            "active_task_id": self.active_task_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        state = cls()
        if not isinstance(data, dict):
            return state
        raw_turns = data.get("turns")
        if isinstance(raw_turns, list):
            for t in raw_turns:
                if isinstance(t, dict) and "role" in t and "text" in t:
                    state.turns.append({"role": str(t["role"]), "text": str(t["text"])})
        raw_tasks = data.get("tasks")
        if isinstance(raw_tasks, list):
            for td in raw_tasks:
                if isinstance(td, dict):
                    try:
                        state.tasks.append(TaskProposal.from_dict(td))
                    except Exception:
                        continue  # skip malformed task
        active = data.get("active_task_id")
        if active and any(t.id == active for t in state.tasks):
            state.active_task_id = active
        return state
