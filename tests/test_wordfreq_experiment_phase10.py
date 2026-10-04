# -*- coding: utf-8 -*-
"""Phase 10 (revisited) tests — extraction audit, size invariants, wordfreq experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import frequency_prior as FP  # noqa: E402

PKG_DATA = ROOT / "src" / "sayit" / "core" / "knowledge" / "data"
INDEX = PKG_DATA / "knowledge_index.json"


class TestFrequencyPrior:
    def test_ordinary_phrase_high_frequency(self):
        assert FP.ordinary_frequency("i need a fast api") > 0.6

    def test_rare_token_low_frequency(self):
        assert FP.ordinary_frequency("postjsql zxqwerty") < 0.3

    def test_penalty_engages_on_ordinary(self):
        p = FP.FrequencyPrior(max_penalty=0.15, threshold=0.7)
        assert p.penalty("i need a fast api") >= 0.0  # ordinary -> may penalize

    def test_penalty_zero_on_rare(self):
        p = FP.FrequencyPrior()
        assert p.penalty("postjsql") == 0.0

    def test_disabled_returns_zero(self):
        p = FP.FrequencyPrior(enabled=False)
        assert p.penalty("i need a fast api") == 0.0

    def test_deterministic(self):
        p = FP.FrequencyPrior()
        assert p.penalty("i need a fast api") == p.penalty("i need a fast api")

    def test_failsafe_on_bad_input(self):
        p = FP.FrequencyPrior()
        assert p.penalty(None) == 0.0  # type: ignore
        assert p.penalty("") == 0.0


class TestWordfreqExperimentArtifact:
    def test_decision_is_reject(self):
        f = ROOT / "artifacts" / "phase10" / "wordfreq_experiment.json"
        if not f.exists():
            pytest.skip("experiment not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["decision"].startswith("REJECT")
        # No measurable improvement: FP counts equal.
        assert d["with_freq_prior"]["hard_negative_false_subs"] == \
            d["baseline_9F"]["hard_negative_false_subs"]
        # And technical recall preserved.
        assert d["with_freq_prior"]["technical_term_recall"] == \
            d["baseline_9F"]["technical_term_recall"]


class TestSizeExtractionInvariants:
    def test_runtime_index_is_single_compact_json(self):
        if not PKG_DATA.exists():
            pytest.skip("package data missing")
        files = [p for p in PKG_DATA.rglob("*") if p.is_file()]
        # Only the compact JSON index ships; no raw dataset/audio.
        assert all(p.suffix == ".json" for p in files), [p.name for p in files]
        assert not any(p.suffix == ".wav" for p in files)

    def test_runtime_index_small(self):
        if not INDEX.exists():
            pytest.skip("index missing")
        # Compact: well under 1 MB (measured ~161 KB).
        assert INDEX.stat().st_size < 1_000_000

    def test_no_raw_npm_dump_bundled(self):
        # The 117 MB npm names.json must never be inside the package.
        for p in (ROOT / "src").rglob("names.json"):
            assert p.stat().st_size < 1_000_000, f"raw npm dump bundled: {p}"

    def test_size_report_present(self):
        f = ROOT / "artifacts" / "phase10" / "size_report.md"
        if not f.exists():
            pytest.skip("size report not generated")
        txt = f.read_text(encoding="utf-8")
        assert "161 KB" in txt or "164638" in txt


class TestProductionFrozen:
    def test_flag_default_off(self):
        from src.sayit.core.settings import Settings
        assert Settings().intelligence_experimental_enabled is False

    def test_no_wordfreq_runtime_dependency(self):
        # The experiment must not have added wordfreq to the production package.
        for rel in ("app.py", "core/asr/candidate_ranker.py",
                    "core/asr/intelligence_pipeline.py"):
            src = (ROOT / "src" / "sayit" / rel).read_text(encoding="utf-8")
            assert "import wordfreq" not in src
            assert "frequency_prior" not in src  # experiment stays in tools/

    def test_decoder_frozen(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src
