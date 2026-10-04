# -*- coding: utf-8 -*-
"""Phase 9A tests: decoder contextual-biasing compatibility + no production change.

These tests lock in the executable compatibility finding and guarantee the
experiment did not alter SayIt's production decoding path.

They do NOT require a downloaded model: the sherpa-onnx compatibility behavior
is asserted via a fast isolated construction probe that is skipped if the model
or sherpa_onnx is unavailable, while the production-path and artifact assertions
always run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# --- production decoding path must remain greedy_search (unchanged) ---------

class TestProductionPathUnchanged:
    def test_backend_uses_greedy_search(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(
            encoding="utf-8"
        )
        # The transducer loader must still request greedy_search and NEMO type.
        assert 'decoding_method="greedy_search"' in src
        assert 'model_type="nemo_transducer"' in src
        # Phase 9A must NOT have introduced beam search or hotwords into the
        # production backend.
        assert "modified_beam_search" not in src
        assert "hotwords_file" not in src

    def test_benchmark_tool_is_isolated(self):
        # The experimental tool lives under tools/ and is never imported by the
        # application package.
        assert (ROOT / "tools" / "benchmark_contextual_biasing.py").exists()
        app_src = ROOT / "src" / "sayit"
        for py in app_src.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "benchmark_contextual_biasing" not in text


# --- benchmark tool pure helpers --------------------------------------------

class TestBenchmarkHelpers:
    def _tool(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import benchmark_contextual_biasing as b

        return b

    def test_wer_identical(self):
        b = self._tool()
        errs, words = b.wer("hello world", "hello world")
        assert errs == 0 and words == 2

    def test_wer_substitution(self):
        b = self._tool()
        errs, words = b.wer("push to postgresql", "push to postjsql")
        assert errs == 1 and words == 3

    def test_tech_metrics_recall(self):
        b = self._tool()
        m = b._tech_metrics(
            "push the code to github then run the python script against postgresql",
            "push the code to github then run the python script against postjsql",
        )
        assert "github" in m["recalled_terms"]
        assert "python" in m["recalled_terms"]
        assert "postgresql" not in m["recalled_terms"]  # missed (PostJSQL)
        assert m["tech_term_recall"] == pytest.approx(2 / 3)

    def test_tech_metrics_no_false_sub_on_clean_hyp(self):
        b = self._tool()
        m = b._tech_metrics("let us meet tomorrow", "let us meet tomorrow")
        assert m["false_substitution_tokens"] == []


# --- compatibility finding (artifact-backed; always available after a run) --

class TestCompatibilityArtifact:
    ART = ROOT / "artifacts" / "phase9" / "9A"

    def test_compatibility_artifact_records_incompatibility(self):
        f = self.ART / "compatibility.json"
        if not f.exists():
            pytest.skip("benchmark artifact not generated in this environment")
        data = json.loads(f.read_text(encoding="utf-8"))
        probes = data["probes"]
        # Greedy loads (production config).
        assert probes["greedy_search"]["outcome"] == "loaded"
        # Hotwords require modified_beam_search (greedy rejects them).
        assert probes["greedy_search_plus_hotwords"]["outcome"] == "python_error"
        # NeMo transducer aborts on modified_beam_search.
        assert probes["modified_beam_search"]["outcome"] == "process_abort"
        # => hotwords are not usable on this model.
        assert data["hotwords_usable"] is False

    def test_gate_is_unsafe_incompatible(self):
        f = self.ART / "report.json"
        if not f.exists():
            pytest.skip("benchmark report not generated in this environment")
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["gate"]["decision"] == "UNSAFE/INCOMPATIBLE"
        assert data["contextual"]["contextual_constructible"] is False


# --- live isolated probe (skipped without model/sherpa) ---------------------

class TestLiveCompatibilityProbe:
    def _model_dir(self):
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            return None
        d = Path(base) / "SayIt" / "models" / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        return d if d.is_dir() else None

    def test_modified_beam_search_loads_for_nemo_on_current_runtime(self):
        try:
            import sherpa_onnx
        except Exception:
            pytest.skip("sherpa_onnx not installed")
        # The production runtime is now pinned to the current upstream release
        # that resolved Phase 9A's NeMo modified-beam incompatibility.
        assert sherpa_onnx.__version__ == "1.13.8"
        d = self._model_dir()
        if d is None:
            pytest.skip("Parakeet model not downloaded")
        probe = (
            "import sherpa_onnx,os\n"
            f"m=r'{d}'\n"
            "sherpa_onnx.OfflineRecognizer.from_transducer("
            "encoder=os.path.join(m,'encoder.int8.onnx'),"
            "decoder=os.path.join(m,'decoder.int8.onnx'),"
            "joiner=os.path.join(m,'joiner.int8.onnx'),"
            "tokens=os.path.join(m,'tokens.txt'),"
            "num_threads=2,provider='cpu',"
            "decoding_method='modified_beam_search',model_type='nemo_transducer')\n"
            "print('LOADED')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
        )
        # 1.13.8 supports this construction for the exact Parakeet model.
        assert proc.returncode == 0, proc.stderr
        assert "LOADED" in (proc.stdout or "")
