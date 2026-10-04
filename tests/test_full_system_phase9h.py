# -*- coding: utf-8 -*-
"""Phase 9H tests — full-system validation + production isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "phase9h"


class TestFinalBenchmark:
    def test_full_system_reaches_manual_ceiling(self):
        f = ART / "final_benchmark.json"
        if not f.exists():
            pytest.skip("final benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        full = d["6_9C_9D_9E_9F_9B"]
        manual = d["2_9B"]
        # Automatic full system matches the manually-curated ceiling.
        assert full["technical_term_recall"] >= manual["technical_term_recall"]
        assert full["exact_entity_accuracy"] >= manual["exact_entity_accuracy"]
        assert full["canonical_exact_accuracy"] >= 0.99
        # And must not exceed manual's false substitutions.
        assert full["false_substitution_total"] <= manual["false_substitution_total"]

    def test_personalization_no_regression(self):
        f = ART / "final_benchmark.json"
        if not f.exists():
            pytest.skip("final benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["7_full_plus_personalization"]["false_substitution_total"] <= \
            d["6_9C_9D_9E_9F_9B"]["false_substitution_total"]


class TestFailureModes:
    def test_safe_fallback(self):
        f = ART / "failure_modes.json"
        if not f.exists():
            pytest.skip("failure modes not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["safe_fallback_leaves_unchanged"] is True
        assert d["missing_index"] == "run against postjsql"  # unchanged on no index
        assert d["empty_text"] == ""


class TestStabilityDeterminism:
    def test_no_memory_growth(self):
        f = ART / "stability.json"
        if not f.exists():
            pytest.skip("stability not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        # Allow a small slack; expect ~0 growth over 50 cycles.
        assert d["rss_growth_mib"] <= 25.0

    def test_determinism(self):
        f = ART / "performance.json"
        if not f.exists():
            pytest.skip("performance not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["deterministic_x3"] is True


class TestPrivacySecurity:
    def test_audit_clean(self):
        f = ART / "privacy_security_audit.json"
        if not f.exists():
            pytest.skip("audit not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["clean"] is True
        for name, info in d["modules"].items():
            assert info["clean"], f"{name}: {info}"


class TestKnowledgeVersioning:
    def test_versions_recorded(self):
        f = ART / "knowledge_versions.json"
        if not f.exists():
            pytest.skip("versions not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["production_sherpa_onnx"] == "1.12.21"
        assert d["production_decoder"] == "greedy_search"


class TestProductionIsolationFinal:
    def test_no_production_import_of_phase9_intelligence(self):
        """The whole Phase 9 intelligence stack must remain unimported by the
        production app/worker/backend (experimental until an explicit ship)."""
        prod = [ROOT / "src" / "sayit" / "app.py",
                ROOT / "src" / "sayit" / "core" / "asr" / "transcription_worker.py",
                ROOT / "src" / "sayit" / "core" / "asr" / "backends.py"]
        forbidden = ("post_context", "candidate_ranker", "ranked_adapter",
                     "core.knowledge", "knowledge.retrieval", "domain_packs",
                     "knowledge.entities", "personalization")
        for p in prod:
            src = p.read_text(encoding="utf-8")
            for f in forbidden:
                assert f not in src, f"{p.name} imports experimental {f}"

    def test_production_decoder_unchanged(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src
        assert "hotwords_file" not in src

    def test_production_sherpa_pin(self):
        import sherpa_onnx
        assert sherpa_onnx.__version__ == "1.13.8"
