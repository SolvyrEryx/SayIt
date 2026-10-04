# -*- coding: utf-8 -*-
"""Phase 10 tests — external-validation infrastructure (validation only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import external_adapter as EA  # noqa: E402
import known_unseen as KU  # noqa: E402


class TestTermExtraction:
    @pytest.mark.parametrize("ref,expected_any", [
        ("Build it with FastAPI and Pydantic", "FastAPI"),
        ("Use Next.js and React", "Next.js"),
        ("install scikit-learn today", "scikit-learn"),
        ("rotate the TLS certificate", "TLS"),
    ])
    def test_extracts_technical(self, ref, expected_any):
        assert expected_any in EA.extract_target_terms(ref)

    def test_ordinary_ref_extracts_little(self):
        # Ordinary prose should yield no CamelCase/acronym/dotted tokens.
        assert EA.extract_target_terms("let us meet tomorrow afternoon") == []


class TestManifest:
    def test_svarah_parse(self, tmp_path):
        root = tmp_path / "svarah"
        root.mkdir()
        (root / "svarah_manifest.json").write_text(
            json.dumps({"audio_filepath": "audio/a.wav", "duration": 1.2,
                        "text": "deploy with FastAPI"}) + "\n", encoding="utf-8")
        entries = EA.parse_svarah(root)
        assert len(entries) == 1
        e = entries[0]
        assert e.source == "svarah"
        assert "FastAPI" in e.target_terms
        assert e.audio_status == "missing"  # audio not actually present

    def test_deterministic_ordering(self, tmp_path):
        root = tmp_path / "svarah"
        root.mkdir()
        lines = [json.dumps({"audio_filepath": f"audio/{n}.wav", "duration": 1,
                             "text": "x"}) for n in ("c", "a", "b")]
        (root / "svarah_manifest.json").write_text("\n".join(lines), encoding="utf-8")
        m1 = EA.build_manifest(tmp_path)
        m2 = EA.build_manifest(tmp_path)
        assert [e.sample_id for e in m1] == [e.sample_id for e in m2]
        assert [e.sample_id for e in m1] == sorted(e.sample_id for e in m1)

    def test_empty_when_no_external(self, tmp_path):
        assert EA.build_manifest(tmp_path) == []

    def test_corrupt_audio_excluded(self, tmp_path):
        root = tmp_path / "svarah"
        root.mkdir()
        (root / "audio").mkdir()
        bad = root / "audio" / "a.wav"
        bad.write_text("not a wav", encoding="utf-8")
        (root / "svarah_manifest.json").write_text(
            json.dumps({"audio_filepath": "audio/a.wav", "text": "x"}), encoding="utf-8")
        entries = EA.build_manifest(tmp_path)
        assert entries[0].audio_status in ("corrupt", "missing")
        assert EA.scored_entries(entries) == []


class TestKnownUnseen:
    def test_known_set_nonempty_readonly(self):
        before = KU.build_known_set()
        assert len(before) > 100  # knowledge system has many surface forms
        after = KU.build_known_set()
        assert before == after  # deterministic, read-only

    def test_classification(self):
        known = KU.build_known_set()
        cls = KU.classify_terms(["FastAPI", "PostgreSQL", "Zxqwerty123"], known)
        assert cls["FastAPI"] == "KNOWN"
        assert cls["PostgreSQL"] == "KNOWN"
        assert cls["Zxqwerty123"] == "UNSEEN"

    def test_no_kb_mutation_on_classify(self):
        # Classifying an UNSEEN term must NOT add it to the known set.
        known = KU.build_known_set()
        KU.classify_terms(["Zxqwerty123"], known)
        assert KU.classify_terms(["Zxqwerty123"], KU.build_known_set())["Zxqwerty123"] == "UNSEEN"

    def test_summary(self):
        known = KU.build_known_set()
        s = KU.summarize([["FastAPI", "UnseenTermXyz"]], known)
        assert s["total_terms"] == 2
        assert s["known"] == 1 and s["unseen"] == 1


class TestArtifacts:
    def test_eval_results_coverage_bound(self):
        f = ROOT / "artifacts" / "phase10" / "evaluation_results.json"
        if not f.exists():
            pytest.skip("eval not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["source_mode"] == "sayit_corpus_selftest":
            # The self-test corpus is coverage-bound: unseen fraction 0.
            assert d["known_unseen"]["unseen_fraction"] == 0.0
        else:
            # External mode (real data staged): must report a real unseen split.
            assert d["source_mode"] == "external"
            assert d["known_unseen"]["unseen_fraction"] is not None

    def test_manifest_present(self):
        f = ROOT / "artifacts" / "phase10" / "manifest.json"
        if not f.exists():
            pytest.skip("eval not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["entry_count"] >= 0


class TestProductionFrozen:
    def test_flag_still_default_off(self):
        from src.sayit.core.settings import Settings
        assert Settings().intelligence_experimental_enabled is False

    def test_no_dataset_in_runtime_package(self):
        # No external speech dataset was bundled into the package.
        data_dir = ROOT / "src" / "sayit" / "core" / "knowledge" / "data"
        for p in data_dir.rglob("*"):
            assert p.suffix != ".wav", f"audio bundled: {p}"
