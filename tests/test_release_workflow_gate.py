"""Structural regression tests for the v0.2.0 Windows/Linux-only release gate.

The signing/release gating lives in GitHub-Actions expression syntax in
.github/workflows/build.yml (not runnable here), so these tests parse the YAML
and assert the exact invariants the release depends on:

* macOS is skipped ONLY for the exact refs/tags/v0.2.0 tag (not generalized).
* The release job proceeds when Windows + Linux succeed AND macOS is either
  successful or skipped-for-v0.2.0, while still requiring the original release
  trigger gating (so unexpected macOS failures on other tags still block it).
* The redundant `release:` trigger was removed (the tag-push run creates the
  release itself).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"


def _load():
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    # PyYAML parses the bare `on:` key as the boolean True.
    triggers = data.get("on", data.get(True))
    return data, triggers


def _norm(s: str) -> str:
    return " ".join(s.split())


def test_macos_skipped_only_for_exact_v020_tag():
    data, _ = _load()
    cond = _norm(data["jobs"]["build-macos"]["if"])
    # Skip is keyed to the EXACT v0.2.0 tag ref, nothing broader.
    assert cond == "${{ github.ref != 'refs/tags/v0.2.0' }}", cond
    # Must not be a blanket "any tag" skip.
    assert "startsWith" not in cond
    assert "refs/tags/v*" not in cond


def test_release_trigger_removed_to_avoid_duplicate_runs():
    _, triggers = _load()
    assert "release" not in triggers, triggers
    # Tag + PR + dispatch remain.
    assert "push" in triggers and "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    assert "v*" in triggers["push"]["tags"]


def test_release_gate_requires_windows_and_linux_success():
    data, _ = _load()
    cond = _norm(data["jobs"]["release"]["if"])
    assert "needs.build-windows.result == 'success'" in cond
    assert "needs.build-linux-x64.result == 'success'" in cond


def test_release_gate_accepts_macos_success_or_v020_skip_only():
    data, _ = _load()
    cond = _norm(data["jobs"]["release"]["if"])
    # macOS must be success OR (skipped AND the v0.2.0 tag) — the skip is not
    # accepted for any other ref.
    assert "needs.build-macos.result == 'success'" in cond
    assert (
        "needs.build-macos.result == 'skipped'" in cond
        and "github.ref == 'refs/tags/v0.2.0'" in cond
    ), cond
    # The skip clause and the v0.2.0 guard must be ANDed together (not a bare
    # 'skipped' acceptance that would let other tags through).
    assert re.search(
        r"needs\.build-macos\.result == 'skipped'\s*&&\s*github\.ref == 'refs/tags/v0\.2\.0'",
        cond,
    ), cond


def test_release_gate_preserves_original_trigger_conditions():
    data, _ = _load()
    cond = _norm(data["jobs"]["release"]["if"])
    # Original publish triggers must still be required.
    assert "startsWith(github.ref, 'refs/tags/v')" in cond
    assert "github.ref == 'refs/heads/main'" in cond
    assert "contains(github.event.head_commit.message, '[release]')" in cond
    # Guarded against cancellation so a skipped dependency does not auto-skip it.
    assert "!cancelled()" in cond


def test_build_macos_still_runs_for_pr_and_other_refs():
    """The skip is a single not-equal to v0.2.0, so PRs/main/other tags build."""
    data, _ = _load()
    cond = data["jobs"]["build-macos"]["if"]
    # Simulate GitHub's evaluation of `github.ref != 'refs/tags/v0.2.0'`.
    for ref, expected_run in [
        ("refs/pull/9/merge", True),
        ("refs/heads/main", True),
        ("refs/heads/feature/v0.2.0-work", True),
        ("refs/tags/v0.2.1", True),
        ("refs/tags/v0.3.0", True),
        ("refs/tags/v0.2.0", False),
    ]:
        runs = ref != "refs/tags/v0.2.0"
        assert runs is expected_run, (ref, cond)
