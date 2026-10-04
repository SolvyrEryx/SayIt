# -*- coding: utf-8 -*-
"""Phase 9K tests — controlled integration behind the off-by-default flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.sayit.core.asr.transcription_worker import TranscriptionWorkerThread
from src.sayit.core.asr.intelligence_pipeline import IntelligencePipeline
from src.sayit.core.context import ContextSignals, resolve_profile
from src.sayit.core.context.profiles import AUTO

ROOT = Path(__file__).resolve().parents[1]


def _run(hyp, ctx_app, pipeline, qtbot):
    tr = MagicMock()
    tr.transcribe_chunked.return_value = hyp
    tr.last_chunk_count = 1
    tr.last_invocation_count = 1
    ctx = resolve_profile(ContextSignals(app_name=ctx_app), detection_enabled=True, override=AUTO)
    w = TranscriptionWorkerThread(
        transcriber=tr, audio_data=np.zeros(1600, dtype=np.float32), sample_rate=16000,
        vocabulary_replacements=[], llm_processor=None, enhancement=None,
        technical_correction_enabled=False, structured_formatting_enabled=False,
        context_resolution=ctx, post_asr_pipeline=pipeline)
    cap = []
    w.finished.connect(lambda *a: cap.append(a))
    w.run()
    return cap[0][0]


class TestFlagOffByteIdentical:
    def test_none_pipeline_unchanged(self, qtbot):
        # With no pipeline (flag off) and 6G/6I/6J disabled, output == raw.
        out = _run("run the python script against postjsql", "code", None, qtbot)
        assert out == "run the python script against postjsql"

    def test_none_pipeline_ordinary_unchanged(self, qtbot):
        out = _run("i need a fast api for the service", "outlook", None, qtbot)
        assert out == "i need a fast api for the service"


class TestFlagOnApplies:
    def test_developer_recovery(self, qtbot):
        pipe = IntelligencePipeline()
        if not pipe.available:
            pytest.skip("packaged index unavailable")
        out = _run("run the python script against postjsql", "code", pipe, qtbot)
        assert "PostgreSQL" in out

    def test_ordinary_preserved_in_email(self, qtbot):
        pipe = IntelligencePipeline()
        if not pipe.available:
            pytest.skip("packaged index unavailable")
        out = _run("i need a fast api for the service", "outlook", pipe, qtbot)
        assert out == "i need a fast api for the service"


class TestFailSafe:
    def test_pipeline_error_does_not_break_worker(self, qtbot):
        class Boom:
            def process(self, *a, **k):
                raise RuntimeError("boom")
        out = _run("run against postjsql", "code", Boom(), qtbot)
        # Worker swallows the pipeline error and keeps the raw text.
        assert out == "run against postjsql"

    def test_missing_index_pipeline_noop(self, qtbot):
        pipe = IntelligencePipeline(index_path=ROOT / "missing.json")
        out = _run("run against postjsql", "code", pipe, qtbot)
        assert out == "run against postjsql"


class TestRollback:
    def test_app_builder_rollback(self):
        from unittest.mock import patch
        import src.sayit.app as app_mod
        with patch.object(app_mod, "AudioRecorder"), patch.object(app_mod, "TranscriptionEngine"), \
             patch.object(app_mod, "HotkeyListener"), patch.object(app_mod, "TextOutputController"), \
             patch.object(app_mod, "SystemTray"), patch.object(app_mod, "RecordingToast"):
            a = app_mod.TranscribeApp()
            a._settings.intelligence_experimental_enabled = True
            a._post_asr_pipeline = None
            _ = a._get_post_asr_pipeline()
            # Disable (rollback) -> builder returns None immediately.
            a._settings.intelligence_experimental_enabled = False
            assert a._get_post_asr_pipeline() is None


class TestArtifacts:
    def test_benchmark_flag_off_byte_identical(self):
        f = ROOT / "artifacts" / "phase9k" / "benchmark.json"
        if not f.exists():
            pytest.skip("9K benchmark not generated")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["flag_off_byte_identical_to_raw"] is True
        assert d["integration"]["default"] is False
        assert d["arms"]["flag_on"]["technical_term_recall"] >= \
            d["arms"]["flag_off"]["technical_term_recall"]


class TestProductionFrozen:
    def test_decoder_unchanged(self):
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "backends.py").read_text(encoding="utf-8")
        assert 'decoding_method="greedy_search"' in src
        assert "modified_beam_search" not in src

    def test_sherpa_pin(self):
        import sherpa_onnx
        assert sherpa_onnx.__version__ == "1.13.8"
