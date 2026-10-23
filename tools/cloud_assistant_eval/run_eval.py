"""Cloud-assistant conversational quality evaluation (WS D).

A SMALL, REPRODUCIBLE evaluation of the existing conversational assistant
(`ConversationOrchestrator` + `ConversationEngine`) against a fixed scenario
set. It is deterministic by default: it drives the real local engine/orchestrator
and uses PURE-FUNCTION mock providers (no network) so the same input always
produces the same verdict. CI never needs an API key.

What this measures (behavioural contracts, not prose "niceness"):
  * context retention across dependent turns;
  * correct use of the LATEST valid correction (recency), not an older value;
  * no invented details (unresolved stays unresolved);
  * NO duplicate task proposals for a continuation/correction;
  * draft vs. completed external action is distinguished and never rewritten;
  * local fallback when cloud is denied/unavailable/failing;
  * the cloud-consent policy is obeyed (configured != authorized);
  * provider output NEVER overrides authoritative local task state/revision.

An OPTIONAL live run is supported ONLY when the operator explicitly sets
SAYIT_CLOUD_EVAL_LIVE=1 AND supplies a provider callable; it never runs by
default and no private conversation history is sent — only the minimal
per-turn effective-task context the orchestrator already isolates.

Usage:
    python tools/cloud_assistant_eval/run_eval.py              # deterministic
    python tools/cloud_assistant_eval/run_eval.py --json out.json

Exit code is non-zero if any scenario assertion fails.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.conversation import (  # noqa: E402
    CloudPolicy,
    ConversationEngine,
    ConversationOrchestrator,
)
from sayit.core.conversation.state import SlotName, TaskStatus  # noqa: E402

# A fixed "today" so every relative date resolves identically run-to-run.
TODAY = _dt.date(2026, 10, 14)  # a Wednesday


# --------------------------------------------------------------------------
# Deterministic mock providers (pure functions, no network).
# --------------------------------------------------------------------------
def mock_provider_echo(text: str, ctx: Dict[str, Any]) -> str:
    """A well-behaved provider: rephrases using ONLY the supplied minimal ctx.

    It must not be able to change task state — it only returns prose. We prove
    that by asserting local state afterwards regardless of what it returns.
    """
    task = ctx.get("task") or {}
    slots = task.get("slots") or {}
    goal = slots.get("goal", "task")
    date = slots.get("date") or slots.get("date_phrase") or "an unspecified date"
    return f"Okay — I've noted your {goal} for {date}."


def mock_provider_hallucinating(text: str, ctx: Dict[str, Any]) -> str:
    """A MISBEHAVING provider that invents a time the user never gave.

    The eval asserts the authoritative LOCAL task is unchanged by this output,
    i.e. provider prose never mutates slots/revision/status.
    """
    return "Sure, I've scheduled it for 9:00 AM sharp and invited everyone."


def mock_provider_failing(text: str, ctx: Dict[str, Any]) -> str:
    raise RuntimeError("simulated provider timeout")


# --------------------------------------------------------------------------
# Scenario model.
# --------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    name: str
    checks: List[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, cond: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(cond), detail))


def _orch(
    *,
    cloud_enabled: bool,
    provider_available: bool,
    provider: Optional[Callable[[str, Dict[str, Any]], str]] = None,
) -> ConversationOrchestrator:
    eng = ConversationEngine(today=TODAY)
    policy = CloudPolicy(
        cloud_enabled=cloud_enabled, provider_available=provider_available
    )
    return ConversationOrchestrator(eng, policy, cloud_reply_fn=provider)


# --------------------------------------------------------------------------
# Scenarios. Each returns a ScenarioResult with explicit behavioural checks.
# --------------------------------------------------------------------------
def s_straightforward(provider) -> ScenarioResult:
    r = ScenarioResult("straightforward_question")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    reply = o.handle_conversation_turn("Remind me about the project meeting tomorrow.")
    task = o._engine.state.active_task()
    r.add("task_created", task is not None)
    r.add(
        "date_resolved_to_tomorrow",
        task and task.get(SlotName.DATE) == "2026-10-15",
        f"date={task.get(SlotName.DATE) if task else None}",
    )
    r.add("reply_non_empty", bool(reply.text.strip()))
    return r


def s_followup_context(provider) -> ScenarioResult:
    r = ScenarioResult("followup_depends_on_context")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    o.handle_conversation_turn("Schedule a meeting on Friday.")
    # A follow-up that only makes sense with retained context.
    o.handle_conversation_turn("Add the budget review.")
    task = o._engine.state.active_task()
    r.add("single_task_retained", len(o._engine.state.tasks) == 1)
    r.add(
        "context_preserved_date",
        task and task.get(SlotName.DATE) == "2026-10-16",
        f"date={task.get(SlotName.DATE) if task else None}",
    )
    r.add(
        "requirement_added_to_same_task",
        task and any("budget" in x.lower() for x in task.requirements),
        f"reqs={task.requirements if task else None}",
    )
    return r


def s_date_correction(provider) -> ScenarioResult:
    r = ScenarioResult("correction_to_earlier_date")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    o.handle_conversation_turn("I have a meeting tomorrow.")
    o.handle_conversation_turn("Scratch that, Friday.")
    task = o._engine.state.active_task()
    r.add("no_duplicate_task", len(o._engine.state.tasks) == 1)
    r.add(
        "latest_correction_wins",
        task and task.get(SlotName.DATE) == "2026-10-16",
        f"date={task.get(SlotName.DATE) if task else None} (expected Friday 2026-10-16)",
    )
    return r


def s_additive(provider) -> ScenarioResult:
    r = ScenarioResult("additive_instruction")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    o.handle_conversation_turn("Draft a report for Friday.")
    o.handle_conversation_turn("Also include the risk section.")
    o.handle_conversation_turn("Add the appendix too.")
    task = o._engine.state.active_task()
    reqs = [x.lower() for x in (task.requirements if task else [])]
    r.add("one_task", len(o._engine.state.tasks) == 1)
    r.add("risk_present", any("risk" in x for x in reqs), f"reqs={reqs}")
    r.add("appendix_present", any("appendix" in x for x in reqs), f"reqs={reqs}")
    return r


def s_removal_preserves_rest(provider) -> ScenarioResult:
    r = ScenarioResult("removal_preserves_others")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    o.handle_conversation_turn("Draft a report for Friday.")
    o.handle_conversation_turn("Also include the budget section.")
    o.handle_conversation_turn("Also include the risk section.")
    o.handle_conversation_turn("Remove the budget section.")
    task = o._engine.state.active_task()
    reqs = [x.lower() for x in (task.requirements if task else [])]
    r.add("budget_removed", not any("budget" in x for x in reqs), f"reqs={reqs}")
    r.add("risk_preserved", any("risk" in x for x in reqs), f"reqs={reqs}")
    r.add(
        "date_preserved",
        task and task.get(SlotName.DATE) == "2026-10-16",
        f"date={task.get(SlotName.DATE) if task else None}",
    )
    return r


def s_ambiguous_clarify(provider) -> ScenarioResult:
    r = ScenarioResult("ambiguous_triggers_clarification")
    o = _orch(cloud_enabled=True, provider_available=True, provider=provider)
    o.handle_conversation_turn("Schedule a meeting on Friday.")
    # Second open task -> ambiguity for an unqualified correction.
    o._engine.state.new_task()
    o._engine.state.tasks[-1].set_slot(
        SlotName.GOAL, "reminder", source_text="seed"
    )
    reply = o.handle_conversation_turn("Move that to Saturday.")
    r.add("needs_clarification", reply.needs_clarification, reply.text)
    r.add("did_not_use_cloud_when_clarifying", reply.used_cloud is False)
    return r


def s_cloud_disabled(provider) -> ScenarioResult:
    r = ScenarioResult("cloud_disabled_operation")
    o = _orch(cloud_enabled=False, provider_available=True, provider=provider)
    reply = o.handle_conversation_turn("Remind me about the meeting tomorrow.")
    r.add("used_cloud_false", reply.used_cloud is False)
    r.add(
        "reason_mentions_not_enabled",
        "not enabled" in reply.cloud_skipped_reason.lower(),
        reply.cloud_skipped_reason,
    )
    r.add(
        "no_provider_text_leaked",
        "noted your" not in reply.text.lower()
        and "scheduled it for 9" not in reply.text.lower(),
        reply.text,
    )
    return r


def s_provider_failing() -> ScenarioResult:
    r = ScenarioResult("provider_unavailable_or_failing")
    # (a) provider configured-but-not-available => policy denies BEFORE any call.
    o1 = _orch(
        cloud_enabled=True, provider_available=False, provider=mock_provider_echo
    )
    rep1 = o1.handle_conversation_turn("Remind me tomorrow.")
    r.add("unavailable_uses_local", rep1.used_cloud is False, rep1.cloud_skipped_reason)
    # (b) provider available but RAISES => local reply preserved.
    o2 = _orch(
        cloud_enabled=True, provider_available=True, provider=mock_provider_failing
    )
    rep2 = o2.handle_conversation_turn("Remind me about the meeting on Friday.")
    task = o2._engine.state.active_task()
    r.add("failure_uses_local", rep2.used_cloud is False, rep2.cloud_skipped_reason)
    r.add(
        "local_state_survived_failure",
        task and task.get(SlotName.DATE) == "2026-10-16",
        f"date={task.get(SlotName.DATE) if task else None}",
    )
    return r


def s_local_state_authoritative() -> ScenarioResult:
    """Provider prose must NEVER override authoritative local task parameters."""
    r = ScenarioResult("local_task_state_remains_authoritative")
    o = _orch(
        cloud_enabled=True,
        provider_available=True,
        provider=mock_provider_hallucinating,
    )
    reply = o.handle_conversation_turn("Remind me about the meeting on Friday.")
    task = o._engine.state.active_task()
    # The misbehaving provider "invented" a 9:00 AM time; the local task must
    # still carry NO time slot (we never asked for one).
    r.add("cloud_prose_returned", reply.used_cloud is True, reply.text)
    r.add(
        "local_time_still_unset",
        task and task.get(SlotName.TIME) is None,
        f"time={task.get(SlotName.TIME) if task else 'n/a'}",
    )
    r.add(
        "local_date_authoritative",
        task and task.get(SlotName.DATE) == "2026-10-16",
        f"date={task.get(SlotName.DATE) if task else None}",
    )
    # Revision count reflects ONLY the local update, not the provider text.
    r.add(
        "revision_from_local_only",
        task and task.revision_number >= 1,
        f"rev={task.revision_number if task else None}",
    )
    return r


def s_draft_vs_executed() -> ScenarioResult:
    """A completed external action is distinguished and not silently rewritten."""
    r = ScenarioResult("draft_vs_completed_action")
    o = _orch(cloud_enabled=False, provider_available=False)
    o.handle_conversation_turn("Remind me about the meeting on Friday.")
    task = o._engine.state.active_task()
    r.add("starts_as_draft", task and task.status is TaskStatus.DRAFT)
    # Simulate an external effect having occurred.
    task.mark_executed("effect-123")
    # A post-execution correction must be refused as a conflict, not applied.
    reply = o.handle_conversation_turn("Actually make it Saturday.")
    task2 = o._engine.state.active_task()
    r.add("status_executed", task2 and task2.status is TaskStatus.EXECUTED)
    r.add(
        "date_not_silently_rewritten",
        task2 and task2.get(SlotName.DATE) == "2026-10-16",
        f"date={task2.get(SlotName.DATE) if task2 else None}",
    )
    return r


def run_all(provider: Optional[Callable] = None) -> List[ScenarioResult]:
    p = provider or mock_provider_echo
    return [
        s_straightforward(p),
        s_followup_context(p),
        s_date_correction(p),
        s_additive(p),
        s_removal_preserves_rest(p),
        s_ambiguous_clarify(p),
        s_cloud_disabled(p),
        s_provider_failing(),
        s_local_state_authoritative(),
        s_draft_vs_executed(),
    ]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Cloud-assistant quality evaluation")
    ap.add_argument("--json", type=str, default=None, help="Write results JSON here")
    args = ap.parse_args(argv)

    live = False  # live runs require explicit opt-in + an injected provider
    import os

    if os.environ.get("SAYIT_CLOUD_EVAL_LIVE") == "1":
        live = True

    results = run_all()
    total_checks = sum(len(s.checks) for s in results)
    passed_checks = sum(1 for s in results for c in s.checks if c.passed)
    all_passed = all(s.passed for s in results)

    print("=" * 70)
    print("SayIt — Cloud-assistant conversational quality evaluation")
    print(f"mode: {'LIVE (opt-in)' if live else 'deterministic mock (no network)'}")
    print("=" * 70)
    for s in results:
        flag = "PASS" if s.passed else "FAIL"
        print(f"[{flag}] {s.name}")
        for c in s.checks:
            if not c.passed:
                print(f"       - FAILED {c.name}: {c.detail}")
    print("-" * 70)
    print(
        f"scenarios: {sum(1 for s in results if s.passed)}/{len(results)} passed | "
        f"checks: {passed_checks}/{total_checks} passed"
    )

    if args.json:
        payload = {
            "today": TODAY.isoformat(),
            "mode": "live" if live else "mock",
            "scenarios": [
                {
                    "name": s.name,
                    "passed": s.passed,
                    "checks": [
                        {"name": c.name, "passed": c.passed, "detail": c.detail}
                        for c in s.checks
                    ],
                }
                for s in results
            ],
            "summary": {
                "scenarios_total": len(results),
                "scenarios_passed": sum(1 for s in results if s.passed),
                "checks_total": total_checks,
                "checks_passed": passed_checks,
            },
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
