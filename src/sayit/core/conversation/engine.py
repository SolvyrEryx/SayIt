"""The conversation engine: deterministic multi-turn intent + self-correction.

``handle_turn(text)`` is the single entry point. It:
  1. detects a self-correction signal (corrections.detect_correction);
  2. extracts structured slots (slots.extract_slots) against the configured
     current date;
  3. applies the change to the ACTIVE task — replacing only affected slots,
     adding/removing requirements, cancelling, or undoing — or starts a new
     task for a genuinely new topic;
  4. resolves references with recency, asking a concise clarification when the
     target is materially ambiguous;
  5. handles corrections after execution honestly (never "rewrites history");
  6. returns a TurnResult describing what changed + whether a reply/clarify is
     needed.

It is fully deterministic and needs no network. An optional LLM can enrich the
natural-language reply, but the engine — not the LLM — owns task state.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import List, Optional

from .corrections import CorrectionKind, CorrectionSignal, detect_correction
from .slots import ExtractedSlots, extract_slots
from .state import ConversationState, SlotName, TaskProposal, TaskStatus


@dataclass
class TurnResult:
    """Outcome of handling one user turn."""

    task: Optional[TaskProposal]
    changed: bool = False
    needs_clarification: bool = False
    clarification: str = ""
    message: str = ""           # human-readable summary of what happened
    correction_kind: str = "none"
    started_new_task: bool = False
    post_execution_conflict: bool = False


# Slots that a REPLACE correction can target, in extraction order.
_REPLACEABLE = (
    (SlotName.DATE, SlotName.DATE_PHRASE),
    (SlotName.TIME, SlotName.TIME_PHRASE),
)


class ConversationEngine:
    def __init__(self, today: Optional[_dt.date] = None):
        # ``today`` is injected (the app passes the configured local date) so
        # relative dates never depend on a guessed clock.
        self._today = today or _dt.date.today()
        self.state = ConversationState()

    def set_today(self, today: _dt.date) -> None:
        self._today = today

    # ------------------------------------------------------------------
    def handle_turn(self, text: str) -> TurnResult:
        self.state.add_turn("user", text)
        signal = detect_correction(text)
        extracted = extract_slots(text, self._today)

        if signal.kind is CorrectionKind.CANCEL:
            return self._handle_cancel(text)
        if signal.kind is CorrectionKind.UNDO:
            return self._handle_undo(text)
        if signal.kind is CorrectionKind.REMOVE:
            return self._handle_remove(text, signal)
        if signal.kind is CorrectionKind.ADD:
            return self._handle_add(text, signal)
        if signal.kind is CorrectionKind.TITLE:
            return self._handle_title(text, signal)
        if signal.kind is CorrectionKind.REPLACE:
            return self._handle_replace(text, signal, extracted)

        # No correction cue: either continue the active task or start a new one.
        return self._handle_plain(text, extracted)

    # -- plain (new info or new task) -----------------------------------
    def _handle_plain(self, text: str, ex: ExtractedSlots) -> TurnResult:
        active = self.state.active_task()
        has_new_info = any([ex.date_iso or ex.date_phrase, ex.time_24h, ex.goal])

        # Start a NEW task when there is no open active task, OR when the user
        # clearly introduces a different goal (genuinely new topic).
        start_new = False
        if active is None or not active.is_open():
            start_new = True
        elif ex.goal and active.get(SlotName.GOAL) and ex.goal != active.get(SlotName.GOAL):
            # A different explicit goal with no correction cue => new topic.
            start_new = True

        if start_new and has_new_info:
            task = self.state.new_task()
            self._apply_extracted(task, ex, text)
            return TurnResult(
                task=task, changed=True, started_new_task=True,
                correction_kind="none",
                message=f"Started task: {task.effective()['slots']}",
            )

        if active is not None and active.is_open() and has_new_info:
            self._apply_extracted(active, ex, text)
            return TurnResult(task=active, changed=True, message="Updated active task.")

        # Nothing structured to apply; just conversational context.
        return TurnResult(task=active, changed=False, message="No structured change.")

    # -- replace --------------------------------------------------------
    def _handle_replace(self, text: str, sig: CorrectionSignal, ex: ExtractedSlots) -> TurnResult:
        active = self._resolve_target()
        if isinstance(active, TurnResult):  # ambiguity clarification
            return active
        if active is None:
            # No task to correct — treat the payload as a fresh statement.
            return self._handle_plain(text, ex)

        if active.status is TaskStatus.EXECUTED:
            return TurnResult(
                task=active, changed=False, post_execution_conflict=True,
                correction_kind="replace",
                message="That task was already executed; a correction needs an "
                        "explicit modify/cancel of the existing effect.",
            )

        # Apply ONLY the slots present in the correction payload, preserving all
        # unaffected slots. Re-extract from the payload so "scratch that, Friday"
        # updates just the date.
        payload_ex = extract_slots(sig.payload or text, self._today)
        updates = {}
        if payload_ex.date_iso or payload_ex.date_phrase:
            updates[SlotName.DATE_PHRASE] = payload_ex.date_phrase
            updates[SlotName.DATE] = payload_ex.date_iso
        if payload_ex.time_24h:
            updates[SlotName.TIME] = payload_ex.time_24h
            updates[SlotName.TIME_PHRASE] = payload_ex.time_phrase
        if not updates:
            # Replacement with no recognizable slot — keep the raw phrase as
            # subject revision rather than discarding the task.
            if sig.payload:
                active.set_slot(SlotName.SUBJECT, sig.payload, source_text=text)
                return TurnResult(task=active, changed=True, correction_kind="replace",
                                  message="Revised subject.")
            return TurnResult(task=active, changed=False, correction_kind="replace",
                              message="Nothing recognizable to replace.")
        active.update_slots(updates, source_text=text)
        return TurnResult(task=active, changed=True, correction_kind="replace",
                          message=f"Replaced {sorted(k.value for k in updates)}.")

    # -- title (subject rename) -----------------------------------------
    def _handle_title(self, text: str, sig: CorrectionSignal) -> TurnResult:
        """Update ONLY the task title (subject), preserving all other slots.

        Reuses the shared target resolver so an ambiguous reference (multiple
        open tasks) asks for clarification instead of guessing, and a
        post-execution correction is surfaced honestly rather than rewritten.
        """
        active = self._resolve_target()
        if isinstance(active, TurnResult):  # ambiguity clarification
            return active
        if active is None:
            return TurnResult(
                task=None, changed=False, needs_clarification=True,
                correction_kind="title",
                clarification="I don't have a task to retitle yet — what's the "
                              "reminder or task about?",
                message="No task to retitle.",
            )
        if active.status is TaskStatus.EXECUTED:
            return TurnResult(
                task=active, changed=False, post_execution_conflict=True,
                correction_kind="title",
                message="That task was already executed; a title change needs an "
                        "explicit modify of the existing effect.",
            )
        new_title = (sig.payload or "").strip()
        if not new_title:
            # Title cue with no target value ("change the title") -> clarify
            # instead of clearing or guessing the title.
            return TurnResult(
                task=active, changed=False, needs_clarification=True,
                correction_kind="title",
                clarification="What should the title be?",
                message="Title correction with no value.",
            )
        active.set_slot(SlotName.SUBJECT, new_title, source_text=text)
        return TurnResult(task=active, changed=True, correction_kind="title",
                          message=f"Retitled to {new_title!r}.")

    # -- add / remove ---------------------------------------------------
    def _handle_add(self, text: str, sig: CorrectionSignal) -> TurnResult:
        active = self._resolve_target()
        if isinstance(active, TurnResult):
            return active
        if active is None:
            task = self.state.new_task()
            task.add_requirement(sig.payload, source_text=text)
            return TurnResult(task=task, changed=True, started_new_task=True,
                              correction_kind="add", message="Started task with requirement.")
        if active.status is TaskStatus.EXECUTED:
            return TurnResult(task=active, changed=False, post_execution_conflict=True,
                              correction_kind="add",
                              message="Task already executed; modify the existing effect explicitly.")
        added = active.add_requirement(sig.payload, source_text=text)
        return TurnResult(task=active, changed=added, correction_kind="add",
                          message=f"Added requirement: {sig.payload}" if added else "Already present.")

    def _handle_remove(self, text: str, sig: CorrectionSignal) -> TurnResult:
        active = self._resolve_target()
        if isinstance(active, TurnResult):
            return active
        if active is None:
            return TurnResult(task=None, changed=False, correction_kind="remove",
                              message="No active task to remove from.")
        if active.status is TaskStatus.EXECUTED:
            return TurnResult(task=active, changed=False, post_execution_conflict=True,
                              correction_kind="remove",
                              message="Task already executed; modify the existing effect explicitly.")
        removed = active.remove_requirement(sig.payload, source_text=text)
        return TurnResult(task=active, changed=removed, correction_kind="remove",
                          message=f"Removed: {sig.payload}" if removed else "Not found.")

    # -- cancel / undo --------------------------------------------------
    def _handle_cancel(self, text: str) -> TurnResult:
        active = self.state.active_task()
        if active is None or not active.is_open():
            return TurnResult(task=active, changed=False, correction_kind="cancel",
                              message="Nothing pending to cancel.")
        if active.status is TaskStatus.EXECUTED:
            return TurnResult(task=active, changed=False, post_execution_conflict=True,
                              correction_kind="cancel",
                              message="Task already executed; cancellation of the external "
                                      "effect needs explicit confirmation.")
        active.cancel(source_text=text)
        return TurnResult(task=active, changed=True, correction_kind="cancel",
                          message="Cancelled the pending task.")

    def _handle_undo(self, text: str) -> TurnResult:
        active = self.state.active_task()
        if active is None or len(active.revisions) == 0:
            return TurnResult(task=active, changed=False, correction_kind="undo",
                              message="Nothing to undo.")
        # Revert the most recent slot revision by restoring its old value.
        last = active.revisions[-1]
        if last.field and last.field in active.slots and last.kind in ("update", "create"):
            if last.old_value is None:
                active.slots.pop(last.field, None)
            else:
                active.slots[last.field] = last.old_value
            active._record("undo", last.field, last.new_value, last.old_value, text)
            return TurnResult(task=active, changed=True, correction_kind="undo",
                              message=f"Undid last change to {last.field}.")
        return TurnResult(task=active, changed=False, correction_kind="undo",
                          message="Last change could not be undone automatically.")

    # -- helpers --------------------------------------------------------
    def _resolve_target(self):
        """Resolve which task a correction refers to.

        Order:
        1. If the active task was already EXECUTED, return it so the caller
           surfaces the post-execution conflict (never silently rewrite it or
           start a new task to dodge it).
        2. A single open task is the target (recency).
        3. Multiple open tasks + an unqualified reference => clarify.
        """
        active = self.state.active_task()
        if active is not None and active.status is TaskStatus.EXECUTED:
            return active
        open_tasks = self.state.open_tasks()
        if len(open_tasks) == 0:
            return None
        if len(open_tasks) == 1:
            self.state.active_task_id = open_tasks[0].id
            return open_tasks[0]
        # Multiple candidates — ambiguous.
        return TurnResult(
            task=None, changed=False, needs_clarification=True,
            clarification="You have more than one task in progress — which one "
                          "should I change?",
            message="Ambiguous correction target.",
        )

    def _apply_extracted(self, task: TaskProposal, ex: ExtractedSlots, src: str) -> None:
        updates = {}
        if ex.goal:
            updates[SlotName.GOAL] = ex.goal
        if ex.subject:
            updates[SlotName.SUBJECT] = ex.subject
        if ex.date_iso or ex.date_phrase:
            updates[SlotName.DATE_PHRASE] = ex.date_phrase
            updates[SlotName.DATE] = ex.date_iso
        if ex.time_24h:
            updates[SlotName.TIME] = ex.time_24h
            updates[SlotName.TIME_PHRASE] = ex.time_phrase
        if updates:
            task.update_slots(updates, source_text=src)
