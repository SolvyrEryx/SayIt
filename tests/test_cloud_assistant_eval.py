"""CI wrapper for the cloud-assistant quality evaluation (WS D).

Runs the deterministic (mock-provider, no-network) evaluation defined in
``tools/cloud_assistant_eval/run_eval.py`` and asserts every behavioural
scenario passes. This keeps the conversational-assistant quality contract
regression-protected without requiring any API key or live provider.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "tools" / "cloud_assistant_eval" / "run_eval.py"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("cloud_assistant_eval", EVAL_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cloud_assistant_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def eval_mod():
    return _load_eval_module()


def test_eval_file_exists():
    assert EVAL_PATH.exists(), f"missing eval harness at {EVAL_PATH}"


def test_all_scenarios_pass_deterministically(eval_mod):
    results = eval_mod.run_all()
    failures = []
    for s in results:
        for c in s.checks:
            if not c.passed:
                failures.append(f"{s.name}.{c.name}: {c.detail}")
    assert not failures, "cloud eval scenario failures:\n" + "\n".join(failures)
    # Sanity: we actually exercised a meaningful number of behavioural checks.
    total_checks = sum(len(s.checks) for s in results)
    assert len(results) >= 10
    assert total_checks >= 25


def test_cloud_consent_policy_blocks_configured_but_unauthorized(eval_mod):
    # A configured provider (present) must NOT be used while cloud is disabled.
    o = eval_mod._orch(
        cloud_enabled=False,
        provider_available=True,
        provider=eval_mod.mock_provider_echo,
    )
    reply = o.handle_conversation_turn("Remind me about the meeting tomorrow.")
    assert reply.used_cloud is False
    assert "not enabled" in reply.cloud_skipped_reason.lower()


def test_provider_output_never_overrides_local_state(eval_mod):
    # The hallucinating provider invents a time; the local task must not gain it.
    from sayit.core.conversation.state import SlotName

    o = eval_mod._orch(
        cloud_enabled=True,
        provider_available=True,
        provider=eval_mod.mock_provider_hallucinating,
    )
    o.handle_conversation_turn("Remind me about the meeting on Friday.")
    task = o._engine.state.active_task()
    assert task is not None
    assert task.get(SlotName.TIME) is None  # provider prose cannot set slots
    assert task.get(SlotName.DATE) == "2026-10-16"


def test_provider_failure_preserves_local_reply(eval_mod):
    from sayit.core.conversation.state import SlotName

    o = eval_mod._orch(
        cloud_enabled=True,
        provider_available=True,
        provider=eval_mod.mock_provider_failing,
    )
    reply = o.handle_conversation_turn("Remind me about the meeting on Friday.")
    assert reply.used_cloud is False
    assert "failed" in reply.cloud_skipped_reason.lower()
    task = o._engine.state.active_task()
    assert task and task.get(SlotName.DATE) == "2026-10-16"
