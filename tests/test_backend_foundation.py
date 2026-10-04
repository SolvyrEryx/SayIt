"""Phase 2 tests: hardware-adaptive backend foundation, honest diagnostics,
extended latency instrumentation, and the measured paste-latency optimization.

These are additive. They assert the production rules:
- the ONLY selectable backend is the validated CPU/Parakeet backend;
- diagnostics never claim GPU acceleration unless a validated accelerated
  backend is actually active;
- capability detection is read-only and separates detected/supported/validated;
- the insertion path no longer carries the removed 100 ms post-paste hold.
"""
from __future__ import annotations

import numpy as np

from sayit.core.asr.backend import (
    AccelerationMode,
    ASRBackend,
    BackendManager,
    ParakeetCPUBackend,
    UnavailableBackend,
    ValidationLevel,
    detect_capabilities,
)
from sayit.core.asr.backend.base import BackendState
from sayit.core.asr.pipeline_timing import PipelineTiming, TimingAggregator
from sayit.core.output.text_output import TextOutputController


class TestBackendAbstraction:
    def test_cpu_backend_is_an_asr_backend(self):
        b = ParakeetCPUBackend()
        assert isinstance(b, ASRBackend)

    def test_cpu_backend_capabilities_are_validated_and_not_accelerated(self):
        caps = ParakeetCPUBackend().capabilities()
        assert caps.name == "parakeet-cpu"
        assert caps.device_kind == "cpu"
        assert caps.validation is ValidationLevel.VALIDATED
        assert caps.accelerated is False
        assert caps.experimental is False

    def test_cpu_backend_wraps_engine_byte_identical(self):
        class FakeEngine:
            is_ready = True
            last_chunk_count = 1
            last_invocation_count = 1

            def transcribe_chunked(self, audio, sr):
                return "exact text"

        b = ParakeetCPUBackend()
        b.attach_engine(FakeEngine())
        assert b.transcribe(np.zeros(16000, dtype=np.float32), 16000) == "exact text"

    def test_attach_engine_sets_ready_without_reload(self):
        class FakeEngine:
            is_ready = True

        b = ParakeetCPUBackend()
        b.attach_engine(FakeEngine())
        assert b.state is BackendState.READY

    def test_unavailable_backend_never_runs(self):
        u = UnavailableBackend("x", "X", "cuda", ("NVIDIA",),
                               ValidationLevel.DETECTED, "note")
        assert u.is_available() is False
        assert u.initialize() is False
        assert u.transcribe(np.zeros(10), 16000) is None
        assert u.capabilities().experimental is True


class TestBackendManager:
    def test_only_cpu_is_selectable(self, monkeypatch):
        # Availability is a model-cache/runtime concern. This unit test is about
        # backend registration, so isolate it from the runner's empty model cache.
        monkeypatch.setattr(ParakeetCPUBackend, "is_available", lambda self: True)
        m = BackendManager(AccelerationMode.AUTO)
        assert m.available_backends() == ["parakeet-cpu"]

    def test_auto_selects_cpu(self):
        m = BackendManager(AccelerationMode.AUTO)
        b = m.select()
        assert b.capabilities().name == "parakeet-cpu"
        assert b.capabilities().validation is ValidationLevel.VALIDATED

    def test_gpu_mode_falls_back_to_cpu_today(self):
        m = BackendManager(AccelerationMode.GPU)
        b = m.select()
        assert b.capabilities().device_kind == "cpu"

    def test_fallback_to_cpu(self):
        m = BackendManager(AccelerationMode.AUTO)
        m.select()
        assert m.fallback_to_cpu().capabilities().name == "parakeet-cpu"

    def test_experimental_backend_cannot_be_registered_as_selectable(self):
        m = BackendManager(AccelerationMode.AUTO)
        before = set(m.available_backends())
        m.register(UnavailableBackend(
            "parakeet-directml", "Parakeet DirectML", "directml",
            ("NVIDIA", "AMD", "Intel"), ValidationLevel.SUPPORTED, "experimental"))
        assert set(m.available_backends()) == before


class TestHonestDiagnostics:
    def test_diag_distinguishes_detected_supported_validated(self):
        d = BackendManager(AccelerationMode.AUTO).diagnostics()
        assert d["backends"]["cpu"] == "validated"
        assert "experimental" in d["backends"]["directml"]
        assert d["backends"]["vulkan"] == "unvalidated"

    def test_active_asr_never_claims_acceleration_without_validated_accel(self):
        d = BackendManager(AccelerationMode.AUTO).diagnostics()
        assert d["active_asr"]["accelerated"] is False
        assert d["active_asr"]["status"] == "CPU"

    def test_roadmap_backends_marked_experimental(self):
        d = BackendManager(AccelerationMode.AUTO).diagnostics()
        assert d["roadmap"], "roadmap should list future backends"
        for entry in d["roadmap"]:
            assert entry["experimental"] is True
            assert entry["accelerated"] is False


class TestCapabilityDetection:
    def test_detection_is_readonly_and_never_raises(self):
        cap = detect_capabilities()
        assert cap.os_name
        assert cap.cpu_logical is None or cap.cpu_logical >= 1

    def test_detection_separates_driver_from_runtime(self):
        cap = detect_capabilities()
        assert isinstance(cap.cuda_driver_present, bool)
        assert isinstance(cap.cuda_runtime_present, bool)
        assert isinstance(cap.directml_present, bool)
        assert isinstance(cap.vulkan_present, bool)


class TestTimingExtensions:
    def test_new_stage_derivations(self):
        t = PipelineTiming(job_id=1)
        t.mark("recording_stop", 0.0)
        t.mark("recorder_finalized", 0.01)
        t.mark("asr_handoff", 0.012)
        t.mark("preprocess_start", 0.012)
        t.mark("preprocess_end", 0.013)
        t.mark("intelligence_start", 0.9)
        t.mark("intelligence_end", 1.0)
        t.mark("clipboard_write_start", 1.0)
        t.mark("clipboard_write_end", 1.006)
        t.mark("paste_start", 1.006)
        t.mark("paste_end", 1.036)
        t.mark("insertion_start", 1.0)
        t.mark("insertion_end", 1.036)
        t.mark("ui_visible", 1.05)

        assert abs(t.recorder_finalize_overhead - 0.01) < 1e-9
        assert abs(t.handoff_overhead - 0.002) < 1e-9
        assert abs(t.preprocess_overhead - 0.001) < 1e-9
        assert abs(t.intelligence_overhead - 0.1) < 1e-9
        assert abs(t.clipboard_overhead - 0.006) < 1e-9
        assert abs(t.paste_overhead - 0.03) < 1e-9
        assert abs(t.insertion_overhead - 0.036) < 1e-9
        assert abs(t.ui_overhead - 0.014) < 1e-9
        assert abs(t.stop_to_text - 1.036) < 1e-9

    def test_aggregator_percentiles(self):
        agg = TimingAggregator()
        for ms in range(1, 11):
            t = PipelineTiming(job_id=ms)
            t.mark("paste_start", 0.0)
            t.mark("paste_end", ms / 1000.0)
            agg.add(t)
        assert agg.count == 10
        st = agg.stats()["paste_overhead"]
        assert st["n"] == 10
        assert st["max"] == 10.0
        assert st["p50"] <= st["p95"] <= st["max"]


class TestPasteOptimization:
    def test_pre_paste_settle_constant_small(self):
        assert TextOutputController.PRE_PASTE_SETTLE_S <= 0.05
        assert TextOutputController.PRE_PASTE_SETTLE_S >= 0.0

    def test_output_text_copies_and_issues_paste(self, monkeypatch):
        import sayit.core.output.text_output as to

        copied = {}
        monkeypatch.setattr(to.pyperclip, "copy", lambda s: copied.setdefault("v", s))
        monkeypatch.setattr(to.TextOutputController, "PRE_PASTE_SETTLE_S", 0.0)

        ctrl = TextOutputController()

        class FakeKb:
            def pressed(self, *_):
                class C:
                    def __enter__(self_): return self_
                    def __exit__(self_, *a): return False
                return C()

            def tap(self, *_):
                return None

        ctrl._keyboard = FakeKb()
        res = ctrl.output_text("hello world")
        assert res.copied is True
        assert res.paste_issued is True
        assert copied["v"] == "hello world"
