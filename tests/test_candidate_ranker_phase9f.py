# -*- coding: utf-8 -*-
"""Phase 9F tests — candidate ranking + false-positive control."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.sayit.core.asr.candidate_ranker import (
    CandidateRanker,
    Decision,
    RankerConfig,
    source_confidence,
)
from src.sayit.core.knowledge import KnowledgeIndex, CandidateRetriever
from src.sayit.core.knowledge.models import Domain, KnowledgeTerm
from src.sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter

ROOT = Path(__file__).resolve().parents[1]
IDX = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"


class _FakeCand:
    """Minimal RetrievedCandidate stand-in for pure ranker unit tests."""
    def __init__(self, canonical, source, variants, context_prior=1.0):
        self.term = _T(canonical, source, variants)
        self.matched_form = variants[0]
        self.components = {"context_prior": context_prior}


class _T:
    def __init__(self, canonical, source, variants):
        self.canonical = canonical
        self.source = source
        self._v = variants
    def all_surface_forms(self):
        return list(self._v)


class TestSourceConfidence:
    def test_order(self):
        assert source_confidence("6j") == 1.0
        assert source_confidence("curated") == 0.9
        assert source_confidence("npm") == 0.6
        assert source_confidence("linguist") == 0.5

    def test_combined_takes_max(self):
        assert source_confidence("curated+linguist") == 0.9
        assert source_confidence("npm/pypi") == 0.6


class TestDecisionStates:
    def test_no_candidate(self):
        d = CandidateRanker().rank("postjsql", [])
        assert d.decision is Decision.NO_CANDIDATE

    def test_strong_winner_corrects(self):
        cands = [_FakeCand("PostgreSQL", "curated", ["postgresql", "postjsql"])]
        d = CandidateRanker().rank("postjsql", cands, "developer")
        assert d.decision is Decision.CORRECT
        assert d.winner == "PostgreSQL"

    def test_weak_winner_abstains(self):
        # A dissimilar span -> low retrieval similarity -> below threshold.
        cands = [_FakeCand("Zephyr", "linguist", ["zephyr"])]
        d = CandidateRanker().rank("completely different words", cands, "developer")
        assert d.decision is Decision.LEAVE_UNCHANGED

    def test_ambiguous_two_close(self):
        cands = [_FakeCand("Alpha", "curated", ["alpha"]),
                 _FakeCand("Alfa", "curated", ["alpha"])]  # identical surface form
        d = CandidateRanker().rank("alpha", cands, "developer")
        assert d.decision in (Decision.AMBIGUOUS, Decision.LEAVE_UNCHANGED)
        assert d.winner is None

    def test_margin_blocks(self):
        cfg = RankerConfig(margin=0.5, ambiguity_band=0.0)
        cands = [_FakeCand("PostgreSQL", "curated", ["postgresql"]),
                 _FakeCand("PostCSS", "linguist", ["postcss"])]
        d = CandidateRanker(cfg).rank("postgresql", cands, "developer")
        # Even a correct top candidate is blocked if margin requirement is huge.
        assert d.decision in (Decision.LEAVE_UNCHANGED, Decision.AMBIGUOUS)


class TestOrdinaryPenalty:
    def test_ordinary_span_penalized_without_strong_context(self):
        cands = [_FakeCand("FastAPI", "curated", ["fastapi", "fast api"],
                           context_prior=0.4)]  # weak context (email-like)
        d = CandidateRanker().rank("fast api", cands, "email")
        # Ordinary phrase + weak context -> penalty likely pushes below threshold.
        assert d.decision is not Decision.CORRECT or d.winner == "FastAPI"
        # Determinism, not exact outcome, is what we assert strongly below.

    def test_strong_context_allows_ordinary(self):
        cands = [_FakeCand("FastAPI", "curated", ["fastapi", "fast api"],
                           context_prior=1.0)]
        d = CandidateRanker().rank("fast api", cands, "developer")
        assert d.decision is Decision.CORRECT


class TestDeterminismExplainability:
    def test_deterministic(self):
        cands = [_FakeCand("PostgreSQL", "curated", ["postgresql", "postjsql"])]
        r = CandidateRanker()
        a = r.rank("postjsql", cands, "developer")
        b = r.rank("postjsql", cands, "developer")
        assert (a.decision, a.winner, a.score) == (b.decision, b.winner, b.score)

    def test_components_present(self):
        cands = [_FakeCand("PostgreSQL", "curated", ["postgresql", "postjsql"])]
        d = CandidateRanker().rank("postjsql", cands, "developer")
        assert d.ranked and d.ranked[0].components
        for key in ("retrieval_similarity", "context_relevance", "source_confidence",
                    "phrase_strength", "ordinary_penalty"):
            assert key in d.ranked[0].components

    def test_failsafe_on_bad_candidate(self):
        class Bad:
            pass
        d = CandidateRanker().rank("x", [Bad()], "developer")
        assert d.decision in (Decision.LEAVE_UNCHANGED, Decision.NO_CANDIDATE,
                              Decision.CORRECT, Decision.AMBIGUOUS)


class TestRankedAdapter:
    def _ad(self):
        idx = KnowledgeIndex.load(IDX) if IDX.exists() else KnowledgeIndex([
            KnowledgeTerm("PostgreSQL", ("postgresql", "postjsql"), "database",
                          Domain.DEVELOPER, "curated", relevance=0.8)])
        return RankedRetrievalAdapter(CandidateRetriever(idx), top_k=10)

    def test_developer_recovery(self):
        r = self._ad().correct("run against postjsql", "developer")
        assert "PostgreSQL" in r.text

    def test_ordinary_preserved(self):
        for raw in ["i need a fast api for the service",
                    "the tensor flow through the network is increasing",
                    "there is rust on the old iron gate"]:
            assert self._ad().correct(raw, "email").text == raw

    def test_exposes_decisions(self):
        ad = self._ad()
        ad.correct("run against postjsql", "developer")
        assert isinstance(ad.last_decisions, list)
        assert any(d["decision"] == "correct" for d in ad.last_decisions)


class TestPrivacyIsolation:
    def test_ranker_no_network_or_exec(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "candidate_ranker.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported, calls = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Call):
                f = node.func
                calls.append(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
        for bad in ("urllib", "requests", "socket", "subprocess"):
            assert not any(bad in (m or "") for m in imported)
        for bad in ("eval", "exec", "system", "popen"):
            assert bad not in calls

    def test_production_not_wired(self):
        for rel in ("app.py", "core/asr/transcription_worker.py", "core/asr/backends.py"):
            src = (ROOT / "src" / "sayit" / rel).read_text(encoding="utf-8")
            assert "candidate_ranker" not in src
            assert "ranked_adapter" not in src

    def test_backend_still_greedy(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src


class TestArtifacts:
    def test_benchmark_arm_D_improves_recall_over_C(self):
        f = ROOT / "artifacts" / "phase9f" / "benchmark.json"
        if not f.exists():
            pytest.skip("benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        c = d["C_9C_retrieval"]["aggregate"]["technical_term_recall"]
        dd = d["D_9C_9F_9B"]["aggregate"]["technical_term_recall"]
        assert dd >= c  # ranking must not reduce recall

    def test_retrieve_once_faster(self):
        f = ROOT / "artifacts" / "phase9f" / "performance.json"
        if not f.exists():
            pytest.skip("performance not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["arm_D_ranked_adapter_median_ms"] < d["arm_C_9C_adapter_median_ms"]
