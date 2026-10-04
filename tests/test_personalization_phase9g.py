# -*- coding: utf-8 -*-
"""Phase 9G tests — explicit personalization."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.sayit.core.knowledge.personalization import (
    PersonalizationStore,
    personalized_terms,
    vocab_entry_to_term,
)
from src.sayit.core.transcript_processor.vocabulary import VocabularyEntry
from src.sayit.core.knowledge import CandidateRetriever, KnowledgeIndex
from src.sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter

ROOT = Path(__file__).resolve().parents[1]
IDX9E = ROOT / "artifacts" / "phase9e" / "knowledge_index_entity.json"


class TestMapping:
    def test_entry_to_term(self):
        t = vocab_entry_to_term(VocabularyEntry(spoken="my project x", written="ProjectXyz",
                                                usage_count=3))
        assert t.canonical == "ProjectXyz"
        assert t.source == "6j"
        assert "my project x" in t.all_surface_forms()

    def test_personalized_terms_enabled_only(self):
        vocab = [{"spoken": "a", "written": "A", "enabled": True},
                 {"spoken": "b", "written": "B", "enabled": False}]
        terms = personalized_terms(vocab)
        assert len(terms) == 1 and terms[0].canonical == "A"

    def test_empty_fallback(self):
        assert personalized_terms([]) == []
        assert personalized_terms(None) == []


class TestLifecycle:
    def test_inspect_disable_delete_clear(self):
        s = PersonalizationStore([
            {"spoken": "x", "written": "X", "enabled": True},
            {"spoken": "y", "written": "Y", "enabled": True}])
        assert len(s.inspect()) == 2
        assert s.disable("x") == 1
        assert len(s.enabled_terms()) == 1
        assert s.delete("y") == 1
        assert len(s.inspect()) == 1
        s.clear()
        assert s.inspect() == []


class TestPersonalizationBehavior:
    def _ad(self, user_terms):
        if not IDX9E.exists():
            pytest.skip("entity index not built")
        retr = CandidateRetriever(KnowledgeIndex.load(IDX9E), user_terms=user_terms)
        return RankedRetrievalAdapter(retr, top_k=10)

    def test_recovery(self):
        ut = personalized_terms([{"spoken": "my project x", "written": "ProjectXyz",
                                  "enabled": True, "usage_count": 3}])
        out = self._ad(ut).correct("deploy my project x now", "developer").text
        assert "ProjectXyz" in out

    def test_disabled_inactive(self):
        ut = personalized_terms([{"spoken": "my project x", "written": "ProjectXyz",
                                  "enabled": False, "usage_count": 5}])
        out = self._ad(ut).correct("deploy my project x now", "developer").text
        assert "ProjectXyz" not in out

    def test_zero_personalization_matches_global(self):
        base = self._ad([]).correct("run against postjsql", "developer").text
        assert "PostgreSQL" in base  # global model still works with no personalization

    def test_conflict_deterministic(self):
        ut = personalized_terms([
            {"spoken": "my db", "written": "PostgreSQL", "enabled": True},
            {"spoken": "my db", "written": "MongoDB", "enabled": True}])
        ad = self._ad(ut)
        assert ad.correct("connect to my db", "developer").text == ad.correct("connect to my db", "developer").text


class TestNoPassiveLearning:
    def test_module_has_no_learning_or_io(self):
        src = (ROOT / "src" / "sayit" / "core" / "knowledge" / "personalization.py").read_text(encoding="utf-8")
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
        for bad in ("urllib", "requests", "socket", "subprocess", "open"):
            assert not any(bad == (m or "") for m in imported)
        for bad in ("eval", "exec", "system", "popen"):
            assert bad not in calls


class TestArtifacts:
    def test_no_regression(self):
        f = ROOT / "artifacts" / "phase9g" / "benchmark.json"
        if not f.exists():
            pytest.skip("benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        a, b = d["baseline_no_personalization"], d["with_explicit_vocab"]
        assert b["false_substitution_total"] <= a["false_substitution_total"]
        assert b["ordinary_preservation"] >= a["ordinary_preservation"]

    def test_lifecycle_artifact(self):
        f = ROOT / "artifacts" / "phase9g" / "lifecycle_conflict.json"
        if not f.exists():
            pytest.skip("lifecycle not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["zero_personalization_equals_baseline"] is True
        assert d["conflict_deterministic"] is True
        assert d["disabled_entry_inactive"] is True
        assert d["after_clear_count"] == 0
