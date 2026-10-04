# -*- coding: utf-8 -*-
"""Phase 9A.2 tests — evaluation instrument + production isolation.

Covers the pure metric functions, corpus/label validation, artifact schema, and
production-freeze guards. Model-dependent benchmark numbers are asserted from
artifacts when present (skipped otherwise); the metric/validator units always
run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "phase9a2"
ART = ROOT / "artifacts" / "phase9" / "9A2"
sys.path.insert(0, str(TOOLS))

import corpus_validator as CV  # noqa: E402
import metrics as M  # noqa: E402


# --- metrics ----------------------------------------------------------------

class TestMetrics:
    def test_wer_identical(self):
        assert M.wer("hello world", "hello world") == (0, 2)

    def test_wer_one_sub(self):
        assert M.wer("push to postgresql", "push to postjsql") == (1, 3)

    def test_technical_recall(self):
        n, d, lst = M.technical_term_recall(
            "push to github then run python against postjsql",
            ["GitHub", "Python", "PostgreSQL"],
        )
        assert (n, d) == (2, 3)
        assert "PostgreSQL" not in lst

    def test_exact_entity_case_sensitive(self):
        # Normalized recall sees 'github'; exact entity requires 'GitHub'.
        hyp = "push to github"
        assert M.term_recognized_normalized(hyp, "GitHub") is True
        assert M.term_present_exact(hyp, "GitHub") is False
        assert M.term_present_exact("push to GitHub", "GitHub") is True

    def test_phrase_recall(self):
        n, d, lst = M.phrase_recall(
            "configure github actions and docker compose",
            ["GitHub Actions", "Docker Compose", "Redis"],
        )
        # Only multi-word phrases counted; both present.
        assert (n, d) == (2, 2)

    def test_false_substitution(self):
        n, lst = M.false_technical_substitutions("i need a fastapi", ["FastAPI"])
        assert n == 1 and "FastAPI" in lst
        n2, _ = M.false_technical_substitutions("i need a fast api", ["FastAPI"])
        assert n2 == 0

    def test_ordinary_preserved(self):
        assert M.ordinary_language_preserved("i need a fast api", ["FastAPI"]) is True
        assert M.ordinary_language_preserved("i need a fastapi", ["FastAPI"]) is False

    def test_aggregate(self):
        recs = [
            {"errors": 1, "ref_words": 10, "tech_recalled": 2, "tech_total": 3,
             "exact_count": 2, "exact_total": 3, "phrase_recalled": 0,
             "phrase_total": 0, "false_sub_count": 0, "has_negatives": False,
             "ordinary_preserved": None},
            {"errors": 0, "ref_words": 8, "tech_recalled": 0, "tech_total": 0,
             "exact_count": 0, "exact_total": 0, "phrase_recalled": 0,
             "phrase_total": 0, "false_sub_count": 0, "has_negatives": True,
             "ordinary_preserved": True},
        ]
        agg = M.aggregate(recs)
        assert agg["wer"] == pytest.approx(1 / 18)
        assert agg["technical_term_recall"] == pytest.approx(2 / 3)
        assert agg["ordinary_preservation"] == 1.0


# --- corpus validation ------------------------------------------------------

class TestCorpusValidation:
    def test_valid_entry(self):
        e = {"id": "X", "reference": "hi", "target_terms": [], "negative_terms": [],
             "category": "ordinary", "synthetic": False}
        assert CV.validate_entry(e) == []

    def test_missing_keys(self):
        assert CV.validate_entry({"id": "X"}) != []

    def test_bad_category(self):
        e = {"id": "X", "reference": "hi", "target_terms": [], "negative_terms": [],
             "category": "nonsense", "synthetic": False}
        assert any("category" in err for err in CV.validate_entry(e))

    def test_labels_file_valid(self):
        f = ART / "labels.json"
        if not f.exists():
            pytest.skip("labels.json missing")
        entries = json.loads(f.read_text(encoding="utf-8"))
        result = CV.validate_corpus(entries)
        assert result["ok"], result
        # A-E are present and not needing recording.
        ids = {e["id"] for e in entries}
        assert {"A", "B", "C", "D", "E"} <= ids

    def test_scored_entries_excludes_needs_recording(self):
        f = ART / "labels.json"
        if not f.exists():
            pytest.skip("labels.json missing")
        entries = json.loads(f.read_text(encoding="utf-8"))
        scored = CV.scored_entries(entries)
        for e in scored:
            assert e.get("needs_recording", False) is False


# --- artifact schema --------------------------------------------------------

class TestArtifacts:
    def test_final_report_flags_and_gate(self):
        f = ART / "final_report.json"
        if not f.exists():
            pytest.skip("final_report.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["gate_decision"] in {"A", "B", "C", "D"}
        flags = d["flags"]
        assert flags["PRODUCTION_CHANGED"] == "NO"
        assert flags["API_KEYS_ADDED"] == "NO"
        assert flags["EXTERNAL_NETWORK_AT_RUNTIME"] == "NO"
        assert flags["PRODUCTION_DEPENDENCY_CHANGED"] == "NO"
        assert flags["MODEL_FILES_CHANGED"] == "NO"

    def test_benchmark_raw_three_arms(self):
        f = ART / "benchmark_raw.json"
        if not f.exists():
            pytest.skip("benchmark_raw.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        if "arm_A_greedy" not in d:
            pytest.skip("no scorable audio at generation time")
        for arm in ("arm_A_greedy", "arm_B_beam", "arm_C_hotword"):
            assert arm in d
            assert "summary" in d[arm]
            assert d[arm]["summary"]["all_deterministic"] is True


# --- production isolation ---------------------------------------------------

class TestProductionIsolation:
    def test_production_sherpa_pin(self):
        import sherpa_onnx

        assert sherpa_onnx.__version__ == "1.12.21"

    def test_production_backend_greedy(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(
            encoding="utf-8"
        )
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src
        assert "hotwords_file" not in src

    def test_app_does_not_import_phase9a2(self):
        app_src = ROOT / "src" / "sayit"
        for py in app_src.rglob("*.py"):
            t = py.read_text(encoding="utf-8")
            assert "phase9a2" not in t
            assert "phase9a1" not in t

    def test_model_dir_untouched(self):
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            pytest.skip("no LOCALAPPDATA")
        md = Path(base) / "SayIt" / "models" / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        if not md.is_dir():
            pytest.skip("model not present")
        assert not (md / "bpe.vocab").exists()
        assert not (md / "bpe.model").exists()

    def test_eval_references_immutable(self):
        # A-E references in labels must match the original eval-audio .txt files.
        f = ART / "labels.json"
        eval_dir = ROOT / "artifacts" / "phase6" / "eval-audio"
        if not f.exists() or not eval_dir.exists():
            pytest.skip("labels or eval-audio missing")
        entries = {e["id"]: e for e in json.loads(f.read_text(encoding="utf-8"))}
        for cid in ("A", "B", "C", "D", "E"):
            ref_file = eval_dir / f"{cid}.txt"
            if ref_file.exists():
                assert entries[cid]["reference"].strip() == ref_file.read_text(
                    encoding="utf-8"
                ).strip()
