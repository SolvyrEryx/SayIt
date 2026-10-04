# -*- coding: utf-8 -*-
"""Phase 9E tests — proper names + rare entity intelligence (conservative)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sayit.core.knowledge.entities import (
    ENTITY_PACKS,
    Entity,
    entity_stats,
    entity_terms,
)
from src.sayit.core.knowledge import KnowledgeIndex, CandidateRetriever
from src.sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter

ROOT = Path(__file__).resolve().parents[1]
IDX9E = ROOT / "artifacts" / "phase9e" / "knowledge_index_entity.json"


class TestEntityModel:
    def test_to_knowledge_term_carries_ambiguity(self):
        e = Entity("apple", "Apple", "organization", ambiguity_class="ordinary")
        kt = e.to_knowledge_term()
        assert kt.canonical == "Apple"
        assert kt.metadata["ambiguity_class"] == "ordinary"
        assert kt.metadata["entity_type"] == "organization"

    def test_entity_terms_valid(self):
        for t in entity_terms():
            assert t.is_valid()

    def test_stats(self):
        s = entity_stats()
        assert set(s) == set(ENTITY_PACKS)
        assert all(v["count"] > 0 for v in s.values())


class TestConservativeAmbiguity:
    def _ad(self):
        if not IDX9E.exists():
            pytest.skip("entity index not built")
        return RankedRetrievalAdapter(CandidateRetriever(KnowledgeIndex.load(IDX9E)), top_k=10)

    @pytest.mark.parametrize("text,ctx,risky", [
        ("i ate an apple for lunch", "chat", "Apple"),
        ("michael jordan was a great player", "chat", "Jordan"),
        ("we sailed down the amazon river", "chat", "Amazon"),
        ("i need to go to the store", "chat", "Go"),
        ("that was a swift decision", "email", "Swift"),
        ("there is rust on the gate", "email", "Rust"),
        ("the python slithered away", "chat", "Python"),
    ])
    def test_ambiguous_entity_left_unchanged(self, text, ctx, risky):
        out = self._ad().correct(text, ctx).text
        assert out == text, f"ambiguous entity wrongly changed: {out!r}"

    @pytest.mark.parametrize("text,want", [
        ("we call open ai from the worker", "OpenAI"),
        ("push to git hub", "GitHub"),
        ("deploy with kubernetes", "Kubernetes"),
    ])
    def test_recovery_in_developer_context(self, text, want):
        out = self._ad().correct(text, "developer").text
        assert want in out


class TestArtifacts:
    def test_no_regression_vs_9d(self):
        f = ROOT / "artifacts" / "phase9e" / "benchmark.json"
        if not f.exists():
            pytest.skip("benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        a, b = d["9F_9D"], d["9F_9D_9E"]
        # Entities must not regress recall/exact/false-subs on the main corpus.
        assert b["technical_term_recall"] >= a["technical_term_recall"]
        assert b["exact_entity_accuracy"] >= a["exact_entity_accuracy"]
        assert b["false_substitution_total"] <= a["false_substitution_total"]

    def test_entity_hard_negatives_zero_false_subs(self):
        f = ROOT / "artifacts" / "phase9e" / "hard_negative_results.json"
        if not f.exists():
            pytest.skip("hard negatives not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["false_sub_count"] == 0


class TestProductionIsolation:
    def test_app_worker_do_not_import_entities(self):
        for rel in ("app.py", "core/asr/transcription_worker.py", "core/asr/backends.py"):
            src = (ROOT / "src" / "sayit" / rel).read_text(encoding="utf-8")
            assert "knowledge.entities" not in src and "import entities" not in src
