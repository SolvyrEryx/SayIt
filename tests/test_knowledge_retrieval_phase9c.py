# -*- coding: utf-8 -*-
"""Phase 9C tests — local knowledge + contextual candidate retrieval."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.sayit.core.knowledge import (
    CandidateRetriever,
    KnowledgeIndex,
)
from src.sayit.core.knowledge.models import (
    Domain,
    KnowledgeTerm,
    normalize_compact,
    normalize_text,
)
from src.sayit.core.knowledge.adapter import (
    RetrievalCorrectionAdapter,
    knowledge_term_to_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
IDX = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"


def _toy_index():
    return KnowledgeIndex([
        KnowledgeTerm("PostgreSQL", ("postgresql", "postgres", "postjsql",
                      "post dre sql"), "database", Domain.DEVELOPER, "curated", relevance=0.8),
        KnowledgeTerm("WebAuthn", ("webauthn", "webant", "web auth"), "protocol",
                      Domain.SECURITY, "curated", relevance=0.75),
        KnowledgeTerm("FastAPI", ("fastapi", "fast api"), "framework",
                      Domain.DEVELOPER, "curated", relevance=0.6),
        KnowledgeTerm("Python", ("python",), "language", Domain.DEVELOPER,
                      "linguist", relevance=0.6),
    ])


class TestModels:
    def test_normalize(self):
        assert normalize_text("Next.js!") == "next js"
        assert normalize_compact("Next.js") == "nextjs"

    def test_surface_forms_dedup(self):
        t = KnowledgeTerm("PostgreSQL", ("postgresql", "PostgreSQL", "postgres"))
        forms = t.all_surface_forms()
        assert "postgresql" in forms and "postgres" in forms
        assert len(forms) == len(set(forms))

    def test_roundtrip(self):
        t = KnowledgeTerm("X", ("x1", "x2"), "cat", Domain.AI_ML, "npm", relevance=0.3)
        assert KnowledgeTerm.from_dict(t.to_dict()).to_dict() == t.to_dict()


class TestIndex:
    def test_build_stats(self):
        idx = _toy_index()
        assert idx.term_count == 4
        s = idx.stats()
        assert s["ngram_postings"] > 0 and s["exact_forms"] > 0

    def test_candidate_ids_bounded(self):
        idx = _toy_index()
        ids = idx.candidate_ids("postjsql", max_pool=10)
        assert 0 in ids  # PostgreSQL (id 0)
        assert len(ids) <= 10

    def test_save_load_roundtrip(self, tmp_path):
        idx = _toy_index()
        p = tmp_path / "idx.json"
        idx.save(p)
        idx2 = KnowledgeIndex.load(p)
        assert idx2.term_count == idx.term_count


class TestRetrieval:
    def test_top1_recovery(self):
        r = CandidateRetriever(_toy_index())
        for span, want in [("postjsql", "PostgreSQL"), ("post dre sql", "PostgreSQL"),
                           ("webant", "WebAuthn")]:
            cands = r.retrieve(span, "developer", top_k=5)
            assert cands and cands[0].term.canonical == want

    def test_top_k_limit(self):
        r = CandidateRetriever(_toy_index())
        assert len(r.retrieve("post", "developer", top_k=2)) <= 2

    def test_context_downweights_developer_in_email(self):
        r = CandidateRetriever(_toy_index())
        dev = r.retrieve("fast api", "developer", top_k=1)[0].score
        email = r.retrieve("fast api", "email", top_k=1)[0].score
        assert email < dev  # email context lowers developer-term score

    def test_deterministic(self):
        r = CandidateRetriever(_toy_index())
        a = [c.term.canonical for c in r.retrieve("postjsql", "developer", top_k=5)]
        b = [c.term.canonical for c in r.retrieve("postjsql", "developer", top_k=5)]
        assert a == b

    def test_empty_span(self):
        r = CandidateRetriever(_toy_index())
        assert r.retrieve("", "developer") == []

    def test_failsafe_none_index(self):
        r = CandidateRetriever(None)
        assert r.retrieve("postjsql", "developer") == []


class TestUserPriority:
    def test_6j_user_term_boosted(self):
        user = [KnowledgeTerm("MyProjectX", ("my project x", "myprojectx"),
                "project", Domain.DEVELOPER, "6j", relevance=0.9)]
        r = CandidateRetriever(_toy_index(), user_terms=user)
        cands = r.retrieve("my project x", "developer", top_k=5)
        assert cands and cands[0].term.canonical == "MyProjectX"


class TestFallback:
    def test_missing_index_uses_fallback(self):
        fb = [KnowledgeTerm("PostgreSQL", ("postgresql", "postjsql"), "database",
              Domain.DEVELOPER, "curated", relevance=0.8)]
        r = CandidateRetriever(None, fallback_terms=fb)
        cands = r.retrieve("postjsql", "developer", top_k=5)
        assert cands and cands[0].term.canonical == "PostgreSQL"

    def test_corrupt_index_load_raises_cleanly(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(Exception):
            KnowledgeIndex.load(bad)


class TestAdapterAndHardNegatives:
    def _adapter(self):
        idx = KnowledgeIndex.load(IDX) if IDX.exists() else _toy_index()
        return RetrievalCorrectionAdapter(CandidateRetriever(idx), top_k=10)

    def test_developer_recovery(self):
        ad = self._adapter()
        r = ad.correct("run against postjsql", "developer")
        assert "PostgreSQL" in r.text

    def test_ordinary_preserved_in_email(self):
        ad = self._adapter()
        for raw in ["i need a fast api for the service",
                    "the tensor flow through the network is increasing",
                    "there is rust on the old iron gate"]:
            r = ad.correct(raw, "email")
            assert r.text == raw

    def test_term_to_candidate_protected_ordinary(self):
        t = KnowledgeTerm("FastAPI", ("fastapi", "fast api"))
        cand = knowledge_term_to_candidate(t)
        assert cand.protected_ordinary is True
        t2 = KnowledgeTerm("PostgreSQL", ("postgresql", "postjsql"))
        assert knowledge_term_to_candidate(t2).protected_ordinary is False


class TestPrivacySecurity:
    def test_no_network_or_exec_in_runtime_modules(self):
        base = ROOT / "src" / "sayit" / "core" / "knowledge"
        for rel in ("models.py", "index.py", "retrieval.py", "adapter.py", "__init__.py"):
            src = (base / rel).read_text(encoding="utf-8")
            tree = ast.parse(src)
            imported, calls = [], []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported += [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
                elif isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        calls.append(f.id)
                    elif isinstance(f, ast.Attribute):
                        calls.append(f.attr)
            for bad in ("urllib", "requests", "socket", "http", "subprocess"):
                assert not any(bad in (m or "") for m in imported), f"{rel} imports {bad}"
            for bad in ("eval", "exec", "system", "popen"):
                assert bad not in calls, f"{rel} calls {bad}"


class TestProductionIsolation:
    def test_worker_app_do_not_import_knowledge(self):
        for rel in ("app.py", "core/asr/transcription_worker.py"):
            src = (ROOT / "src" / "sayit" / rel).read_text(encoding="utf-8")
            assert "core.knowledge" not in src and "knowledge.retrieval" not in src

    def test_backend_still_greedy(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src


class TestArtifacts:
    def test_final_report_gate_and_flags(self):
        f = ROOT / "artifacts" / "phase9" / "9C" / "final_report.json"
        if not f.exists():
            pytest.skip("final_report.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["gate_decision"] in {"A", "B", "C", "D", "E"}
        for k in ("PRODUCTION_CHANGED", "API_KEYS_ADDED", "EXTERNAL_NETWORK_AT_RUNTIME"):
            assert d["flags"][k] == "NO"

    def test_source_manifest_records_licenses(self):
        f = ROOT / "artifacts" / "phase9" / "9C" / "source_manifest.json"
        if not f.exists():
            pytest.skip("source_manifest.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["runtime_network"] is False
        assert any("linguist" in s["source"].lower() for s in d["sources"])
