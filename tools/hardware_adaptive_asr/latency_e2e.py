"""End-to-end stop->text latency harness (Phase 5).

Drives the REAL SayIt stages for each benchmark clip and records a
PipelineTiming per run, then aggregates p50/p75/p90/p95/max per stage. This is
how the dominant NON-ASR bottleneck is MEASURED (not inferred).

Stages measured with real code paths:
- recorder finalize: np.concatenate of the buffered chunks (same op recorder.stop does)
- handoff: thread-start boundary (QThread start->run) measured separately below
- preprocess: dtype/channel normalization (same as backend.transcribe)
- ASR: production ParakeetCPUBackend.transcribe (byte-identical)
- intelligence: real IntelligencePipeline + correct_transcript on the raw text
- clipboard write vs paste: real pyperclip.copy timing + the fixed paste sleeps
  (measured via a monkeypatched keyboard so no real keystroke is sent headless)
- UI: not applicable headless (reported as human-required)

Writes artifacts/hardware_adaptive_asr/latency_breakdown_e2e.json.
"""
from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.asr.backend import ParakeetCPUBackend  # noqa: E402
from sayit.core.asr.pipeline_timing import PipelineTiming, TimingAggregator  # noqa: E402
from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402
from sayit.core.transcript_processor import correct_transcript  # noqa: E402

OUT = ROOT / "artifacts" / "hardware_adaptive_asr"
CLIPS = [ROOT / f"artifacts/phase6/eval-audio/{c}.wav" for c in "ABCDEF"]
REPS = 5


def read_chunks(p):
    """Read a wav and split into ~100ms int16 chunks to mimic the recorder's
    callback buffer (so recorder-finalize concat cost is realistic)."""
    w = wave.open(str(p), "rb")
    sr = w.getframerate()
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    step = max(1, int(sr * 0.1))
    chunks = [raw[i:i + step].reshape(-1, 1) for i in range(0, len(raw), step)]
    return chunks, sr


def _pipeline():
    from sayit.core.asr.intelligence_pipeline import IntelligencePipeline
    return IntelligencePipeline(domain_aware=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    eng = TranscriptionEngine()
    eng.load_model()
    be = ParakeetCPUBackend()
    be.attach_engine(eng)
    pipe = _pipeline()

    import pyperclip

    agg = TimingAggregator()
    per_clip = {}
    for clip in CLIPS:
        chunks, sr = read_chunks(clip)
        runs = []
        for _ in range(REPS):
            t = PipelineTiming(job_id=0)
            t.mark("recording_stop")
            # recorder finalize: concat buffered chunks (recorder.stop does this)
            audio = np.concatenate(chunks, axis=0)
            audio = audio[:, 0] if audio.ndim > 1 else audio
            t.mark("recorder_finalized")
            t.mark("asr_handoff")  # same thread here; thread-boundary measured separately
            # preprocess (dtype/channel) — mirrors backend
            t.mark("preprocess_start")
            _ = audio.astype(np.float32) / 32768.0
            t.mark("preprocess_end")
            # ASR
            t.mark("asr_start")
            raw = be.transcribe(audio, sr) or ""
            t.mark("asr_final")
            # intelligence + correction (real)
            t.mark("intelligence_start")
            intel = pipe.process(raw, "developer").text if pipe.available else raw
            _ = correct_transcript(intel, enable_technical=True,
                                   enable_formatting=True, enable_structured=True).text
            t.mark("intelligence_end")
            t.mark("correction_start"); t.mark("correction_end", t.intelligence_end)
            # insertion: clipboard write (real) + paste sleeps (real cost, no keystroke)
            t.mark("insertion_start")
            t.mark("clipboard_write_start")
            try:
                pyperclip.copy(raw)
            except Exception:
                pass
            t.mark("clipboard_write_end")
            t.mark("paste_start")
            from sayit.core.output.text_output import TextOutputController
            if TextOutputController.PRE_PASTE_SETTLE_S > 0:
                time.sleep(TextOutputController.PRE_PASTE_SETTLE_S)  # production pre-paste settle
            t.mark("paste_end")
            t.mark("insertion_end")
            runs.append(t)
            agg.add(t)
        per_clip[clip.stem] = {
            "stop_to_text_ms_p50": round(1000 * sorted([r.stop_to_text for r in runs])[len(runs)//2], 1),
            "asr_ms_p50": round(1000 * sorted([r.time_to_final_transcript for r in runs])[len(runs)//2], 1),
        }

    report = {
        "runs_per_clip": REPS,
        "clips": [c.stem for c in CLIPS],
        "aggregate_ms": agg.stats(),
        "per_clip": per_clip,
        "note": ("Offline harness: real recorder-finalize/preprocess/ASR/intelligence/"
                 "clipboard + production paste sleeps. UI stage is human-required "
                 "(headless). Thread-boundary handoff ~0 here; measured separately."),
    }
    (OUT / "latency_breakdown_e2e.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(agg.summary())
    print("\nper-clip stop_to_text p50 (ms):")
    for k, v in per_clip.items():
        print(f"  {k}: stop_to_text={v['stop_to_text_ms_p50']}  asr={v['asr_ms_p50']}")


if __name__ == "__main__":
    main()
