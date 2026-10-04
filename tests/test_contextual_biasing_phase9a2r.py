# -*- coding: utf-8 -*-
"""Phase 9A.2R tests — recording ingest loop + plumbing self-test.

These verify the record -> ingest -> re-run machinery works the moment valid
audio appears, WITHOUT fabricating speech. They also assert production remains
frozen. No microphone or real recordings are required to run them.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "phase9a2"
ART = ROOT / "artifacts" / "phase9" / "9A2R"
sys.path.insert(0, str(TOOLS))

import ingest_status as ING  # noqa: E402
import plumbing_selftest as PS  # noqa: E402


def _write_wav(path, sr=16000, ch=1, width=2, seconds=0.3):
    frames = int(seconds * sr)
    data = np.zeros(frames * ch, dtype=np.int16)
    w = wave.open(str(path), "wb")
    w.setnchannels(ch)
    w.setsampwidth(width)
    w.setframerate(sr)
    w.writeframes(data.tobytes())
    w.close()


class TestWavSpec:
    def test_valid_spec(self, tmp_path):
        p = tmp_path / "ok.wav"
        _write_wav(p, sr=16000, ch=1, width=2)
        spec = ING.wav_spec(p)
        assert spec["spec_ok"] is True
        assert spec["sample_rate"] == 16000 and spec["channels"] == 1

    def test_wrong_sample_rate(self, tmp_path):
        p = tmp_path / "bad.wav"
        _write_wav(p, sr=8000)
        assert ING.wav_spec(p)["spec_ok"] is False

    def test_stereo_rejected(self, tmp_path):
        p = tmp_path / "stereo.wav"
        _write_wav(p, ch=2)
        assert ING.wav_spec(p)["spec_ok"] is False

    def test_missing_file(self, tmp_path):
        assert ING.wav_spec(tmp_path / "nope.wav")["spec_ok"] is False


class TestIngestStatus:
    def test_build_status_counts(self, tmp_path, monkeypatch):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        _write_wav(corpus / "X.wav")  # valid
        entries = [
            {"id": "X", "wav": "X.wav", "reference": "r", "target_terms": [],
             "negative_terms": [], "category": "ordinary", "synthetic": False,
             "needs_recording": True},
            {"id": "Y", "wav": "Y.wav", "reference": "r", "target_terms": [],
             "negative_terms": [], "category": "ordinary", "synthetic": False,
             "needs_recording": True},
        ]
        monkeypatch.setattr(ING, "CORPUS", corpus)
        monkeypatch.setattr(ING, "EVAL", corpus)
        status = ING.build_status(entries)
        assert status["audio_present"] == 1
        assert status["valid_spec"] == 1
        assert status["missing"] == 1
        assert "Y" in status["blocking_ids"]
        assert "X" not in status["blocking_ids"]
        assert status["recording_complete"] is False

    def test_apply_updates_flips_only_valid(self, tmp_path, monkeypatch):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        _write_wav(corpus / "X.wav")           # valid -> should flip
        _write_wav(corpus / "Z.wav", sr=8000)  # invalid -> should NOT flip
        entries = [
            {"id": "X", "wav": "X.wav", "reference": "r", "target_terms": [],
             "negative_terms": [], "category": "ordinary", "synthetic": False,
             "needs_recording": True},
            {"id": "Z", "wav": "Z.wav", "reference": "r", "target_terms": [],
             "negative_terms": [], "category": "ordinary", "synthetic": False,
             "needs_recording": True},
        ]
        monkeypatch.setattr(ING, "CORPUS", corpus)
        monkeypatch.setattr(ING, "EVAL", corpus)
        status = ING.build_status(entries)
        n = ING.apply_updates(entries, status)
        assert n == 1
        flags = {e["id"]: e["needs_recording"] for e in entries}
        assert flags["X"] is False
        assert flags["Z"] is True


class TestPlumbingSelfTest:
    def test_loop_proven(self):
        r = PS.run_selftest()
        assert r["valid_before"] == 1
        assert r["invalid_before"] == 1
        assert r["missing_before"] == 1
        assert r["updated"] == 1
        assert r["tmp_ok_still_blocking"] is False
        assert r["tmp_badspec_blocking"] is True
        assert r["tmp_missing_blocking"] is True


class TestIngestedRecordings:
    """After real recording ingest: 18 user clips committed under content-verified
    IDs; corpus has real audio; PYTHON/RUST pairs remain pending."""

    def test_corpus_has_real_recordings(self):
        corpus = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
        wavs = sorted(p.name for p in corpus.glob("*.wav")) if corpus.exists() else []
        if not wavs:
            pytest.skip("recordings not ingested in this environment")
        # The 8 recorded discriminators (both halves) must be present.
        for pid in ("FASTAPI", "PG", "OPENAI", "NEXTJS", "SQLALCHEMY",
                    "TENSORFLOW", "WEBAUTHN", "KUBECTL"):
            assert f"PAIR_{pid}_ORDINARY.wav" in wavs
            assert f"PAIR_{pid}_TECHNICAL.wav" in wavs
        assert "MULTI01.wav" in wavs and "MIXED01.wav" in wavs

    def test_ingested_wavs_meet_capture_spec(self):
        corpus = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
        if not corpus.exists() or not list(corpus.glob("*.wav")):
            pytest.skip("recordings not ingested")
        for p in corpus.glob("*.wav"):
            spec = ING.wav_spec(p)
            assert spec["spec_ok"], f"{p.name} failed spec: {spec}"

    def test_python_rust_still_pending(self):
        f = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
        if not f.exists():
            pytest.skip("labels missing")
        import json as _json
        entries = {e["id"]: e for e in _json.loads(f.read_text(encoding="utf-8"))}
        for cid in ("PAIR_PYTHON_ORDINARY", "PAIR_RUST_TECHNICAL"):
            if cid in entries:
                assert entries[cid].get("needs_recording") is True

    def test_status_reports_post_ingest(self):
        f = ART / "recording_status.json"
        if not f.exists():
            pytest.skip("recording_status.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        # 23 real clips present/valid (5 A-E + 18 ingested); 4 still blocking.
        assert d["valid_spec"] >= 23
        assert len(d["blocking_ids"]) == 4


class TestProductionIsolation:
    def test_production_sherpa_pin(self):
        import sherpa_onnx

        assert sherpa_onnx.__version__ == "1.13.8"

    def test_backend_greedy_unchanged(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(
            encoding="utf-8"
        )
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src

    def test_app_does_not_import_phase9(self):
        for py in (ROOT / "src" / "sayit").rglob("*.py"):
            t = py.read_text(encoding="utf-8")
            assert "phase9a2" not in t and "phase9a1" not in t
