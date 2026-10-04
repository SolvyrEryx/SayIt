# -*- coding: utf-8 -*-
"""Phase 9D tests — domain packs + canonical-form quality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sayit.core.knowledge.domain_packs import (
    CONF_OFFICIAL,
    DOMAIN_PACKS,
    DomainTerm,
    canonical_map,
    pack_stats,
    pack_terms,
)
from src.sayit.core.knowledge import KnowledgeIndex, CandidateRetriever
from src.sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter

ROOT = Path(__file__).resolve().parents[1]
IDX9D = ROOT / "artifacts" / "phase9d" / "knowledge_index_domain.json"


class TestCanonicalForms:
    @pytest.mark.parametrize("spoken,canonical", [
        ("fastapi", "FastAPI"),
        ("sqlalchemy", "SQLAlchemy"),
        ("tensorflow", "TensorFlow"),
        ("numpy", "NumPy"),
        ("next js", "Next.js"),
        ("postgresql", "PostgreSQL"),
        ("webauthn", "WebAuthn"),
        ("kubectl", "kubectl"),
        ("github actions", "GitHub Actions"),
    ])
    def test_canonical_map(self, spoken, canonical):
        assert canonical_map().get(spoken) == canonical

    def test_not_generic_titlecase(self):
        # Official casing != naive title-case (e.g. not "Fastapi"/"Sqlalchemy").
        cm = canonical_map()
        assert cm["fastapi"] == "FastAPI" and cm["fastapi"] != "Fastapi"
        assert cm["sqlalchemy"] == "SQLAlchemy" and cm["sqlalchemy"] != "Sqlalchemy"

    def test_ordinary_lowercase_word_not_in_map_as_wrong(self):
        # 'pandas' canonical stays lowercase 'pandas' (official), not 'Pandas'.
        assert canonical_map().get("pandas") == "pandas"


class TestPacks:
    def test_all_terms_have_official_canonical(self):
        for name, terms in DOMAIN_PACKS.items():
            for t in terms:
                assert t.canonical_confidence >= CONF_OFFICIAL or t.canonical_confidence > 0

    def test_pack_stats(self):
        s = pack_stats()
        assert set(s) == set(DOMAIN_PACKS)
        assert all(v["term_count"] > 0 for v in s.values())

    def test_pack_terms_convert(self):
        terms = pack_terms(["web"])
        assert any(t.canonical == "FastAPI" for t in terms)
        for t in terms:
            assert t.is_valid()

    def test_domain_term_to_knowledge_term(self):
        dt = DomainTerm("fastapi", "FastAPI", ("fast api",))
        kt = dt.to_knowledge_term()
        assert kt.canonical == "FastAPI"
        assert "fast api" in kt.all_surface_forms() or "fastapi" in kt.all_surface_forms()


class TestDomainCorrection:
    def _ad(self):
        if not IDX9D.exists():
            pytest.skip("domain index not built")
        return RankedRetrievalAdapter(CandidateRetriever(KnowledgeIndex.load(IDX9D)), top_k=10)

    def test_canonical_recovery(self):
        ad = self._ad()
        r = ad.correct("build the endpoint with fast api and pydantic", "developer")
        assert "FastAPI" in r.text  # official casing, not 'fastapi'

    def test_sqlalchemy_official_casing(self):
        ad = self._ad()
        r = ad.correct("the sql alchemy models are in the project", "developer")
        assert "SQLAlchemy" in r.text

    def test_ordinary_collision_preserved(self):
        ad = self._ad()
        for raw, ctx in [("i saw a spark in the sky", "chat"),
                         ("she went for a run this morning", "email"),
                         ("the express train was late", "email")]:
            assert ad.correct(raw, ctx).text == raw


class TestArtifacts:
    def test_benchmark_canonical_lift(self):
        f = ROOT / "artifacts" / "phase9d" / "benchmark.json"
        if not f.exists():
            pytest.skip("benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        # Arm E (domain) must have >= exact-entity accuracy than arm D (no domain).
        assert d["E_9C_9D_9F_9B"]["exact_entity_accuracy"] >= d["D_9C_9F_9B"]["exact_entity_accuracy"]
        # And canonical-exact should reach a high value.
        assert d["E_9C_9D_9F_9B"]["canonical_exact_accuracy"] >= 0.9

    def test_collisions_clean(self):
        f = ROOT / "artifacts" / "phase9d" / "collision_analysis.json"
        if not f.exists():
            pytest.skip("collision analysis not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert all(not v["changed"] for v in d.values())


class TestProductionIsolation:
    def test_app_worker_do_not_import_domain(self):
        for rel in ("app.py", "core/asr/transcription_worker.py", "core/asr/backends.py"):
            src = (ROOT / "src" / "sayit" / rel).read_text(encoding="utf-8")
            assert "domain_packs" not in src
