# -*- coding: utf-8 -*-
"""Phase 9J tests — IntelligencePipeline safe wiring + feature flag."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sayit.core.asr.intelligence_pipeline import IntelligencePipeline
from src.sayit.core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


class TestFeatureFlag:
    def test_default_off(self):
        s = Settings()
        assert s.intelligence_experimental_enabled is False
        assert s.intelligence_threshold == 0.90

    def test_flag_round_trip(self, tmp_path, monkeypatch):
        import src.sayit.core.settings.settings as sm
        monkeypatch.setattr(sm, "get_config_dir", lambda: tmp_path)
        s = Settings(intelligence_experimental_enabled=True, intelligence_threshold=0.85)
        s.save()
        loaded = Settings.load()
        assert loaded.intelligence_experimental_enabled is True
        assert loaded.intelligence_threshold == 0.85


class TestFailSafe:
    def test_empty_inputs(self):
        p = IntelligencePipeline()
        assert p.process("", "developer").text == ""
        assert p.process("   ", "developer").text == "   "
        assert p.process(None, "developer").text == ""  # type: ignore

    def test_missing_index_is_noop(self):
        p = IntelligencePipeline(index_path=ROOT / "nope_missing.json")
        r = p.process("run against postjsql", "developer")
        assert r.text == "run against postjsql"
        assert r.changed is False
        assert p.available is False

    def test_corrupt_index_is_noop(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        p = IntelligencePipeline(index_path=bad)
        r = p.process("run against postjsql", "developer")
        assert r.text == "run against postjsql" and r.changed is False


class TestPurePostText:
    def test_module_imports_nothing_unsafe(self):
        import ast
        src = (ROOT / "src" / "sayit" / "core" / "asr" / "intelligence_pipeline.py").read_text(encoding="utf-8")
        imports = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imports += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        for bad in ("audio", "recorder", "safezones", "output", "pyperclip",
                    "pynput", "urllib", "requests", "socket", "subprocess"):
            assert not any(bad in (m or "") for m in imports), f"imports {bad}"


class TestBehavior:
    def _p(self):
        p = IntelligencePipeline()
        if not p.available:
            pytest.skip("packaged index unavailable")
        return p

    def test_developer_recovery(self):
        assert "PostgreSQL" in self._p().process("run against postjsql", "developer").text

    def test_ambiguous_conservative_in_email(self):
        assert self._p().process("i need a fast api for the service", "email").text == \
            "i need a fast api for the service"

    def test_no_transcript_in_diagnostics(self):
        p = self._p()
        p.process("run against postjsql", "developer")
        assert "transcript" not in json.dumps(p.last_diagnostics).lower()
        # Diagnostics are counts/flags only.
        assert set(p.last_diagnostics) <= {"applied", "changed", "num_decisions",
                                           "num_corrections", "reason"}


class TestWiredBehindFlag:
    """9K wires the pipeline into the worker BEHIND the off-by-default flag.
    The worker accepts a post_asr_pipeline param; the app builds it only when
    the flag is on and passes None otherwise."""

    def test_worker_accepts_post_asr_pipeline(self):
        import inspect
        from src.sayit.core.asr.transcription_worker import TranscriptionWorkerThread
        params = inspect.signature(TranscriptionWorkerThread.__init__).parameters
        assert "post_asr_pipeline" in params

    def test_app_gates_pipeline_on_flag(self):
        src = (ROOT / "src" / "sayit" / "app.py").read_text(encoding="utf-8")
        # The app builds the pipeline only when the experimental flag is set.
        assert "intelligence_experimental_enabled" in src
        assert "_get_post_asr_pipeline" in src

    def test_flag_off_yields_no_pipeline(self):
        # With the default (off) flag, the builder returns None (byte-identical).
        from unittest.mock import patch
        import src.sayit.app as app_mod
        with patch.object(app_mod, "AudioRecorder"), patch.object(app_mod, "TranscriptionEngine"), \
             patch.object(app_mod, "HotkeyListener"), patch.object(app_mod, "TextOutputController"), \
             patch.object(app_mod, "SystemTray"), patch.object(app_mod, "RecordingToast"):
            a = app_mod.TranscribeApp()
            a._settings.intelligence_experimental_enabled = False
            assert a._get_post_asr_pipeline() is None
            a._settings.intelligence_experimental_enabled = True
            a._post_asr_pipeline = None
            # When on, a pipeline object is returned (or None if index missing).
            p = a._get_post_asr_pipeline()
            assert p is None or hasattr(p, "process")


class TestArtifacts:
    def test_replay_report(self):
        f = ROOT / "artifacts" / "phase9j" / "validation_report.json"
        if not f.exists():
            pytest.skip("9J not run")
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["pure_post_text"]["clean"] is True
        assert d["failsafe"]["missing_index_unchanged"] is True
        assert d["ambiguous_developer_case"]["email"]["became_technical"] is False
        assert d["diagnostics_contains_no_transcript"] is True
