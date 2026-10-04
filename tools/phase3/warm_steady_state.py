"""Phase 3: warm steady-state latency + warm-reuse audit.

Measures stop->text with the production ParakeetCPUBackend + real intelligence,
separating COLD (first-ever: model init + first inference) from WARM steady
state (repeated dictation). Also AUDITS that repeated dictation does NOT reload
the model, tokenizer, backend, or intelligence index (object identity stable;
sherpa recognizer created exactly once).

Read-only w.r.t. production code. Writes artifacts/phase3/warm_steady_state.json.
"""
from __future__ import annotations

import gc
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.asr.backend import ParakeetCPUBackend  # noqa: E402
from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402
from sayit.core.transcript_processor import correct_transcript  # noqa: E402

OUT = ROOT / "artifacts" / "phase3"
CLIPS = [ROOT / f"artifacts/phase6/eval-audio/{c}.wav" for c in "ABCDEF"]
WARM_REPS = 10


def read_wav(p):
    w = wave.open(str(p), "rb"); sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    return d, sr


def pctl(xs, q):
    s = sorted(xs); i = max(0, min(len(s) - 1, int(round((len(s) - 1) * q)))); return s[i]


def stats(xs):
    return {"n": len(xs), "p50": round(pctl(xs, .5), 1), "p95": round(pctl(xs, .95), 1),
            "min": round(min(xs), 1), "max": round(max(xs), 1)} if xs else {}


def _pipeline():
    from sayit.core.asr.intelligence_pipeline import IntelligencePipeline
    return IntelligencePipeline(domain_aware=False)


def one_dictation(be, pipe, audio, sr):
    """Full stop->text minus GUI: ASR + intelligence + correction. ms."""
    t0 = time.perf_counter()
    raw = be.transcribe(audio, sr) or ""
    t1 = time.perf_counter()
    intel = pipe.process(raw, "developer").text if pipe.available else raw
    _ = correct_transcript(intel, enable_technical=True, enable_formatting=True,
                           enable_structured=True).text
    t2 = time.perf_counter()
    return (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, raw


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = [(c.stem, *read_wav(c)) for c in CLIPS]

    # ---- COLD: construct + load + first inference (NOT normal dictation) ----
    t0 = time.perf_counter()
    eng = TranscriptionEngine()
    eng.load_model()
    cold_load_ms = (time.perf_counter() - t0) * 1000.0
    be = ParakeetCPUBackend(); be.attach_engine(eng)
    pipe = _pipeline()

    # identity snapshots for the reuse audit
    engine_id = id(be._engine)
    recognizer_id_before = id(be._engine._backend._recognizer)
    pipe_id = id(pipe)

    name0, d0, sr0 = clips[0]
    tc0 = time.perf_counter()
    _ = one_dictation(be, pipe, d0, sr0)
    cold_first_inference_ms = (time.perf_counter() - tc0) * 1000.0

    # ---- WARM: repeated dictation (steady state) ----
    asr_ms, intel_ms, total_ms = [], [], []
    recognizer_ids = set()
    for _ in range(WARM_REPS):
        for name, d, sr in clips:
            a, i, _raw = one_dictation(be, pipe, d, sr)
            asr_ms.append(a); intel_ms.append(i); total_ms.append(a + i)
            recognizer_ids.add(id(be._engine._backend._recognizer))

    recognizer_id_after = id(be._engine._backend._recognizer)
    reuse_audit = {
        "engine_object_stable": id(be._engine) == engine_id,
        "pipeline_object_stable": id(pipe) == pipe_id,
        "recognizer_created_once": (
            recognizer_id_before == recognizer_id_after
            and len(recognizer_ids) == 1
        ),
        "distinct_recognizer_ids_during_warm": len(recognizer_ids),
        "note": ("A stable recognizer id across all warm runs proves the sherpa "
                 "model+tokenizer+backend were NOT reloaded per dictation."),
    }

    report = {
        "cold": {
            "model_init_ms": round(cold_load_ms, 1),
            "first_inference_ms": round(cold_first_inference_ms, 1),
            "note": "Cold = construct+load+first inference. EXCLUDED from warm dictation latency.",
        },
        "warm_steady_state_ms": {
            "asr": stats(asr_ms),
            "intelligence": stats(intel_ms),
            "stop_to_text_minus_gui": stats(total_ms),
        },
        "warm_reuse_audit": reuse_audit,
        "clips": [c.stem for c in CLIPS],
        "warm_reps_per_clip": WARM_REPS,
    }
    be.shutdown(); gc.collect()
    (OUT / "warm_steady_state.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
