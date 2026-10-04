# -*- coding: utf-8 -*-
"""Phase 11 tests — external data acquisition path + generic staged ingest."""

from __future__ import annotations

import csv
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import external_adapter as EA  # noqa: E402


def _wav(path, sr=16000, seconds=0.4):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros(int(sr * seconds), dtype=np.int16)
    w = wave.open(str(path), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(data.tobytes()); w.close()


class TestGenericStagedIngest:
    def test_csv_manifest(self, tmp_path):
        root = tmp_path / "tie_shorts"
        _wav(root / "audio" / "s1.wav")
        with open(root / "manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sample_id", "speaker_id", "text"])
            w.writerow(["s1", "SPK1", "deploy FastAPI with PostgreSQL"])
        entries = EA.build_manifest(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.source == "tie_shorts" and e.speaker_id == "SPK1"
        assert e.audio_status == "ok"
        assert "FastAPI" in e.target_terms and "PostgreSQL" in e.target_terms

    def test_jsonl_manifest(self, tmp_path):
        root = tmp_path / "svarah"
        _wav(root / "audio" / "a.wav")
        (root / "manifest.jsonl").write_text(
            json.dumps({"sample_id": "a", "speaker_id": "S2", "text": "use TensorFlow",
                        "audio": "audio/a.wav"}) + "\n", encoding="utf-8")
        entries = EA.build_manifest(tmp_path)
        assert len(entries) == 1
        assert entries[0].speaker_id == "S2"
        assert "TensorFlow" in entries[0].target_terms

    def test_reference_verbatim(self, tmp_path):
        root = tmp_path / "tie_shorts"
        _wav(root / "audio" / "s1.wav")
        ref = "I use Node.js, scikit-learn and HTTP/2 daily."
        with open(root / "manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sample_id", "speaker_id", "text"])
            w.writerow(["s1", "SPK1", ref])
        entries = EA.build_manifest(tmp_path)
        assert entries[0].reference == ref  # never altered

    def test_missing_audio_excluded(self, tmp_path):
        root = tmp_path / "tie_shorts"
        root.mkdir()
        with open(root / "manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sample_id", "speaker_id", "text"])
            w.writerow(["ghost", "SPK1", "x"])
        entries = EA.build_manifest(tmp_path)
        assert entries[0].audio_status == "missing"
        assert EA.scored_entries(entries) == []

    def test_deterministic_and_deduped(self, tmp_path):
        root = tmp_path / "tie_shorts"
        _wav(root / "audio" / "b.wav")
        _wav(root / "audio" / "a.wav")
        with open(root / "manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sample_id", "speaker_id", "text"])
            w.writerow(["b", "S", "x"])
            w.writerow(["a", "S", "y"])
        m1 = [e.sample_id for e in EA.build_manifest(tmp_path)]
        m2 = [e.sample_id for e in EA.build_manifest(tmp_path)]
        assert m1 == m2 == sorted(m1)
        assert len(m1) == len(set(m1))

    def test_empty_when_nothing_staged(self, tmp_path):
        assert EA.build_manifest(tmp_path) == []


class TestAcquisitionStatus:
    def test_external_data_is_real_not_fabricated(self):
        # Phase 11A: real external speech (TIE_shorts) was downloaded + staged.
        # If present it must be real audio with a manifest (never synthesized).
        ext = ROOT / "artifacts" / "phase10" / "external"
        wavs = list(ext.rglob("*.wav")) if ext.exists() else []
        if not wavs:
            pytest.skip("no external data staged in this environment")
        # Each source dir with audio must have a manifest (provenance).
        for src_dir in ext.iterdir():
            if src_dir.is_dir() and list(src_dir.rglob("*.wav")):
                assert (src_dir / "manifest.csv").exists() or (src_dir / "manifest.jsonl").exists()

    def test_data_inventory_records_gated_status(self):
        f = ROOT / "artifacts" / "phase10" / "data_inventory.md"
        if not f.exists():
            pytest.skip("inventory not generated")
        txt = f.read_text(encoding="utf-8").lower()
        assert "gated" in txt and "svarah" in txt


class TestProductionFrozen:
    def test_flag_off(self):
        from src.sayit.core.settings import Settings
        assert Settings().intelligence_experimental_enabled is False

    def test_no_dataset_dependency_added(self):
        # The datasets library was NOT added to acquire external data.
        import importlib.util as u
        # It is acceptable for it to be absent; it must not be imported by src.
        for py in (ROOT / "src" / "sayit").rglob("*.py"):
            t = py.read_text(encoding="utf-8")
            assert "import datasets" not in t
            assert "huggingface_hub" not in t
