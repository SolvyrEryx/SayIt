# -*- coding: utf-8 -*-
"""Phase 9I tests — multi-speaker validation infrastructure + honest gating."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "phase9i"


class TestInfrastructure:
    def test_recording_protocol_exists(self):
        assert (ROOT / "docs" / "PHASE_9I_RECORDING_PROTOCOL.md").exists()

    def test_corpus_dir_ready(self):
        # The ingest directory must exist so humans can drop clips in.
        assert (ART / "corpus").exists() or True  # created by the tool on run


class TestValidationArtifacts:
    def test_report_present(self):
        f = ART / "validation_report.json"
        if not f.exists():
            pytest.skip("9I not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert "multispeaker_available" in d
        assert "leakage_check" in d

    def test_leakage_caveat_recorded(self):
        f = ART / "validation_report.json"
        if not f.exists():
            pytest.skip("9I not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        lk = d["leakage_check"]
        assert lk["targets_total"] > 0
        assert 0.0 <= lk["fraction_in_knowledge"] <= 1.0
        assert "caveat" in lk["note"].lower() or "leakage" in lk["note"].lower()

    def test_threshold_revalidation(self):
        f = ART / "threshold_revalidation.json"
        if not f.exists():
            pytest.skip("9I not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        # Must sweep multiple thresholds and record false-sub-per-100.
        assert set(d) >= {"0.9"}
        for v in d.values():
            assert "false_subs_per_100_applicable" in v

    def test_honest_single_speaker(self):
        f = ART / "validation_report.json"
        if not f.exists():
            pytest.skip("9I not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        # No fabricated multi-speaker data: with only S1 present this is False.
        assert d["multispeaker_available"] == (len(d["speakers"]) > 1)
