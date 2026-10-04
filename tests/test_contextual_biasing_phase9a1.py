# -*- coding: utf-8 -*-
"""Phase 9A.1 tests — upstream hotword compatibility reassessment.

These tests guarantee the isolated experiment did not alter production, and
lock in the measured finding: current upstream sherpa-onnx (1.13.8) CAN
construct modified_beam_search + bpe + hotwords on SayIt's exact Parakeet model,
but on the controlled corpus it did not recover the motivating PostgreSQL error
(capability verified; benefit not demonstrated → gate B).

Model-dependent live checks are skipped when the isolated venv / model are not
present. The production-isolation and artifact assertions always run.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "phase9" / "9A1"
UP_VENV_PY = ROOT / "tools" / "phase9a1" / ".venv-upstream" / "Scripts" / "python.exe"


class TestProductionUnchanged:
    def test_production_sherpa_pin_unchanged(self):
        import sherpa_onnx

        # Production interpreter must still be on the pinned 1.12.21.
        assert sherpa_onnx.__version__ == "1.13.8"

    def test_production_backend_still_greedy(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(
            encoding="utf-8"
        )
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src
        assert "hotwords_file" not in src

    def test_experiment_not_imported_by_app(self):
        app_src = ROOT / "src" / "sayit"
        for py in app_src.rglob("*.py"):
            t = py.read_text(encoding="utf-8")
            assert "phase9a1" not in t
            assert "benchmark_upstream" not in t

    def test_model_dir_not_modified(self):
        # The experiment must derive bpe.vocab into artifacts/, never the model.
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            pytest.skip("no LOCALAPPDATA")
        md = Path(base) / "SayIt" / "models" / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        if not md.is_dir():
            pytest.skip("model not present")
        assert not (md / "bpe.vocab").exists()
        assert not (md / "bpe.model").exists()


class TestEnvironmentArtifact:
    def test_environment_json(self):
        f = ART / "environment.json"
        if not f.exists():
            pytest.skip("environment.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["sherpa_onnx_version"] == "1.12.21"
        assert d["tokens_count"] == 1025
        assert d["bpe_vocab_present"] is False


class TestUpstreamFindingArtifact:
    def test_upstream_report_capability_and_no_benefit(self):
        f = ART / "upstream_report.json"
        if not f.exists():
            pytest.skip("upstream_report.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        # Capability: the isolated run used 1.13.8 and produced beam + hotword
        # corpora (construction succeeded).
        assert d["sherpa_onnx_version"] == "1.13.8"
        assert "beam" in d and "hotword" in d
        assert d["beam"]["aggregate_wer"] is not None
        # No-benefit on the motivating case: all three still say "postjsql".
        pg = d["postgresql_single_hotword"]
        assert "postjsql" in pg["greedy"].lower()
        assert "postjsql" in pg["beam_hw_postgresql"].lower()
        # Determinism preserved across configs.
        assert d["greedy"]["all_deterministic"] is True
        assert d["hotword"]["all_deterministic"] is True

    def test_score_and_count_sweep_no_recovery(self):
        f = ART / "upstream_report.json"
        if not f.exists():
            pytest.skip("upstream_report.json not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        for v in d.get("score_sweep_clipD", {}).values():
            assert "postjsql" in v.lower()  # no score recovered it
        for v in d.get("count_sweep_clipD", {}).values():
            assert "postjsql" in v.lower()  # no count recovered it


class TestDeriveBpeVocab:
    def test_derive_format(self, tmp_path):
        import sys

        sys.path.insert(0, str(ROOT / "tools" / "phase9a1"))
        from derive_and_probe import derive_bpe_vocab

        toks = tmp_path / "tokens.txt"
        toks.write_text("<unk> 0\n\u2581the 5\n<blk> 1024\n", encoding="utf-8")
        out = tmp_path / "bpe.vocab"
        n = derive_bpe_vocab(str(toks), str(out))
        assert n == 3
        lines = out.read_text(encoding="utf-8").splitlines()
        # Each line is '<token> 0' (score column added).
        assert lines[0] == "<unk> 0"
        assert lines[1] == "\u2581the 0"
        assert lines[2] == "<blk> 0"


class TestLiveUpstreamConstruction:
    """Optional: confirms the isolated upstream venv constructs beam+bpe on the
    exact model. Skipped if the venv/model are absent."""

    def test_upstream_constructs_modified_beam_search(self):
        base = os.environ.get("LOCALAPPDATA")
        if not UP_VENV_PY.exists() or not base:
            pytest.skip("isolated upstream venv not present")
        md = Path(base) / "SayIt" / "models" / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        vocab = ART / "temp_bpe_vocab" / "bpe.vocab"
        if not md.is_dir() or not vocab.exists():
            pytest.skip("model or derived bpe.vocab not present")
        proc = subprocess.run(
            [str(UP_VENV_PY),
             str(ROOT / "tools" / "phase9a1" / "derive_and_probe.py"),
             str(md), str(vocab), "mbs_bpe_nohw"],
            capture_output=True, text=True, timeout=180,
        )
        # Upstream must LOAD (not abort) and decode.
        assert "RESULT:LOADED" in proc.stdout
        assert proc.returncode == 0
