"""Safe task-action architecture (structure only; no autonomous execution).

This milestone establishes the lifecycle + guards WITHOUT implementing
unrestricted computer control. There is no shell execution, no filesystem
mutation, no autonomous clicking. ``execute`` only runs a narrowly scoped,
explicitly supplied capability callback after confirmation, and records an
idempotency key so a retry/correction cannot duplicate an external effect.

Key guard: ``is_result_current`` lets an async consumer reject a result that was
computed against a stale task revision (Workstream H / Case K), so a late LLM
response can never overwrite a newer corrected state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from .state import TaskProposal, TaskStatus


class ActionError(RuntimeError):
    pass


@dataclass
class ExecutionResult:
    ok: bool
    effect_id: Optional[str] = None
    message: str = ""
    duplicate_suppressed: bool = False


class ActionCoordinator:
    """Validates, confirms, and (optionally) executes task proposals safely."""

    def is_result_current(self, task: TaskProposal, result_revision: int) -> bool:
        """True iff a result computed at ``result_revision`` is still current.

        A stale async response (older revision) must be discarded so it cannot
        overwrite a newer correction.
        """
        return result_revision == task.revision_number

    def missing_required(self, task: TaskProposal, required: list[str]) -> list[str]:
        """Return the required slot names that are not yet filled."""
        return [r for r in required if not task.slots.get(r)]

    def request_confirmation(self, task: TaskProposal, required: list[str]) -> bool:
        """Move a fully-specified DRAFT to AWAITING_CONFIRM. Returns True if ready."""
        if task.status is not TaskStatus.DRAFT:
            return task.status is TaskStatus.AWAITING_CONFIRM
        if self.missing_required(task, required):
            return False
        task.status = TaskStatus.AWAITING_CONFIRM
        task._record("await_confirm", "status", TaskStatus.DRAFT.value,
                     task.status.value, "confirmation requested")
        return True

    def execute(
        self,
        task: TaskProposal,
        capability: Callable[[TaskProposal], str],
        *,
        expected_revision: int,
        confirmed: bool,
    ) -> ExecutionResult:
        """Execute an approved task via a narrow capability callback.

        Guards:
        - must be confirmed and AWAITING_CONFIRM;
        - the caller's ``expected_revision`` must match (no stale execution
          after a correction);
        - idempotent: a second execute for an already-executed task returns the
          existing effect without re-running the capability.
        """
        if task.status is TaskStatus.EXECUTED and task.executed_effect_id:
            return ExecutionResult(
                ok=True, effect_id=task.executed_effect_id,
                message="Already executed; no duplicate effect created.",
                duplicate_suppressed=True,
            )
        if not confirmed:
            raise ActionError("Execution requires explicit confirmation.")
        if task.status is not TaskStatus.AWAITING_CONFIRM:
            raise ActionError(f"Task not awaiting confirmation (status={task.status.value}).")
        if expected_revision != task.revision_number:
            # A correction landed after confirmation; refuse to execute a stale
            # version. The caller must re-confirm the current revision.
            raise ActionError(
                f"Stale revision: confirmed {expected_revision} but current is "
                f"{task.revision_number}; re-confirm the updated task."
            )
        if task.idempotency_key is None:
            task.idempotency_key = uuid.uuid4().hex
        try:
            effect_id = capability(task)
        except Exception as e:  # pragma: no cover - capability-defined
            task.status = TaskStatus.FAILED
            task._record("execute_failed", "status", TaskStatus.AWAITING_CONFIRM.value,
                         task.status.value, str(e))
            return ExecutionResult(ok=False, message=f"Execution failed: {e}")
        task.mark_executed(effect_id)
        return ExecutionResult(ok=True, effect_id=effect_id, message="Executed.")
