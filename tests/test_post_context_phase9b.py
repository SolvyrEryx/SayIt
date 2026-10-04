# -*- coding: utf-8 -*-
"""Phase 9B tests — isolated post-ASR contextual candidate correction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sayit.core.asr.post_context import (
    Candidate,
    CandidatePack,
    CorrectorConfig,
    PostASRContextCorrector,
)
from src.sayit.core.asr.post_context_pack import all_candidates, default_pack

ROOT = Path(__file__).resolve().parents[1]


def _c(cfg=None):
    return PostASRContextCorrector(default_pack(), cfg or CorrectorConfig())


class TestRecovery:
    @pytest.mark.parametrize("raw,expected", [
        ("run against postjsql", "PostgreSQL"),
        ("the post dre sql server", "PostgreSQL"),
        ("uses webant for auth", "WebAuthn"),
        ("we need ubitil here", "kubectl"),
    ])
    def test_mangled_tokens_recovered_in_developer(self, raw, expected):
        r = _c().correct(raw, "developer")
        assert expected in r.text, (raw, r.text)
        assert r.changed


class TestOrdinaryProtection:
    @pytest.mark.parametrize("raw", [
        "i need a fast api for the service",
        "we should open ai research notes",
        "the tensor flow through the network",
        "there is rust on the gate",
        "the python slithered across the rock",
        "react to the event quickly",
    ])
    def test_ordinary_context_preserved(self, raw):
        r = _c().correct(raw, "email")
        assert r.text == raw, f"ordinary speech corrupted: {r.text!r}"

    def test_developer_may_correct_ambiguous(self):
        # In developer context, a protected-ordinary phrase CAN be corrected.
        r = _c().correct("i need a fast api", "developer")
        assert "FastAPI" in r.text


class TestGates:
    def test_below_threshold_unchanged(self):
        # 'postgle' is close-ish to postgresql but NOT an exact listed variant;
        # a very high threshold must leave it unchanged.
        cfg = CorrectorConfig(threshold=0.99)
        r = _c(cfg).correct("run against postgle", "developer")
        assert "PostgreSQL" not in r.text
        assert r.text == "run against postgle"

    def test_margin_blocks_when_two_close_candidates(self):
        # Two candidates with near-identical variants; high margin blocks.
        pack = CandidatePack([
            Candidate("Alpha", ("alpha", "alfa")),
            Candidate("Alfa", ("alfa", "alpha")),
        ])
        c = PostASRContextCorrector(pack, CorrectorConfig(margin=0.3))
        r = c.correct("alpha", "developer")
        # Best and second are tied -> margin gate blocks.
        assert r.text == "alpha"

    def test_negative_context_blocks_candidate(self):
        pack = CandidatePack([
            Candidate("Rust", ("rust",), negative_contexts=("chat",),
                      protected_ordinary=True),
        ])
        c = PostASRContextCorrector(pack, CorrectorConfig())
        # Blocked entirely in chat context.
        r = c.correct("rust", "chat")
        assert r.text == "rust"


class TestSplitMerge:
    def test_multi_word_phrase(self):
        r = _c().correct("set up github actions today", "developer")
        assert "GitHub Actions" in r.text


class TestDeterminism:
    def test_repeatable(self):
        c = _c()
        outs = {c.correct("run against postjsql", "developer").text for _ in range(5)}
        assert len(outs) == 1


class TestExplainability:
    def test_decision_metadata(self):
        r = _c().correct("run against postjsql", "developer")
        changed = [d for d in r.decisions if d.changed]
        assert changed
        d = changed[0]
        assert d.replacement == "PostgreSQL"
        assert d.reason == "corrected"
        assert d.components is not None
        assert 0.0 <= d.best_score <= 1.0
        assert d.margin >= 0.0


class TestFailSafe:
    def test_empty_text(self):
        assert _c().correct("", "developer").text == ""

    def test_whitespace(self):
        assert _c().correct("   ", "developer").text == "   "

    def test_empty_pack(self):
        c = PostASRContextCorrector(CandidatePack([]), CorrectorConfig())
        assert c.correct("run against postjsql", "developer").text == "run against postjsql"

    def test_malformed_candidate_ignored(self):
        pack = CandidatePack([Candidate("X", ("",))])  # empty variant
        c = PostASRContextCorrector(pack, CorrectorConfig())
        # No usable variant -> no change, no crash.
        assert c.correct("hello world", "developer").text == "hello world"

    def test_none_text(self):
        assert _c().correct(None, "developer").text == ""

    def test_unknown_context_defaults_safe(self):
        r = _c().correct("i need a fast api", "banana")
        # Unknown context -> weight default 1.0 is NOT applied (dict.get default
        # 1.0 means normal-ish); ensure no crash and deterministic.
        assert isinstance(r.text, str)


class TestNoProductionIntegration:
    def test_worker_does_not_import_post_context(self):
        worker = (ROOT / "src" / "sayit" / "core" / "asr" / "transcription_worker.py").read_text(encoding="utf-8")
        assert "post_context" not in worker

    def test_app_does_not_import_post_context(self):
        app = (ROOT / "src" / "sayit" / "app.py").read_text(encoding="utf-8")
        assert "post_context" not in app

    def test_backend_still_greedy(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src


class TestArtifacts:
    def test_final_report_gate_and_flags(self):
        f = ROOT / "artifacts" / "phase9" / "9B" / "final_report.json"
        if not f.exists():
            pytest.skip("final_report.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["gate_decision"] in {"A", "B", "C", "D", "E"}
        fl = d["flags"]
        assert fl["PRODUCTION_CHANGED"] == "NO"
        assert fl["API_KEYS_ADDED"] == "NO"
        assert fl["6J_CHANGED"] == "NO"

    def test_ablation_shows_context_reduces_false_subs(self):
        f = ROOT / "artifacts" / "phase9" / "9B" / "ablation.json"
        if not f.exists():
            pytest.skip("ablation.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        # Context must reduce false substitutions vs similarity-only.
        assert d["A_similarity_only"]["false_substitution_total"] > \
            d["B_plus_context"]["false_substitution_total"]
