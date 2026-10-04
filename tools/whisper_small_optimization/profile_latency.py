"""Whisper Small latency profiling harness (production FROZEN; no source changes).

Mirrors the REAL app path:
  SherpaOnnxBackend.transcribe (preprocess = dtype/channel; ASR decode)
  -> SayIt intelligence (IntelligencePipeline, same as ARM B)
  -> deterministic correction/formatting (correct_transcript)

Measures, with perf_counter, per stage:
  preprocess_ms | asr_ms | intelligence_ms | formatting_ms  (= stop->final)

Buckets: SHORT(2-5s), MEDIUM(5-10s), LONG(10-20s) using approved local audio.
Cold vs warm vs repeated-warm. p50/p95 and % of total.

Nothing here changes production. It only loads the SAME engine/model and times
it. Writes CSVs under artifacts/whisper_small_optimization/.
"""
from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.asr import speech_mode as SM  # noqa: E402
from sayit.core.asr.backends import SherpaOnnxBackend  # noqa: E402
from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402
from sayit.core.audio.audio_processor import needs_chunking  # noqa: E402
from sayit.core.transcript_processor import correct_transcript  # noqa: E402

WHISPER = SM.HIGHER_ACCURACY_MODEL_ID
PARAKEET = SM.FAST_MODEL_ID
OUT = ROOT / "artifacts" / "whisper_small_optimization"

# Deterministic approved benchmark clips (all 16 kHz mono).
BENCH = {
    "short": [ROOT / "artifacts/phase6/eval-audio/A.wav"],                 # 4.7s
    "medium": [ROOT / "artifacts/phase6/eval-audio/C.wav",                # 5.4s
               ROOT / "artifacts/phase6/eval-audio/E.wav"],                # 8.6s
    "long": [ROOT / "artifacts/phase6/eval-audio/F.wav",                  # 16.4s
             ROOT / "artifacts/phase10/external/tie_shorts/audio/-tgglZ-XWYk.wav"],  # 19.2s
}


def read_wav(p):
    w = wave.open(str(p), "rb")
    sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    return d, sr


def rss_mib():
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / 1048576, 1)
    except Exception:
        return None


def pctl(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    i = max(0, min(len(s) - 1, int(round((len(s) - 1) * q))))
    return s[i]


def _pipeline():
    """Same SayIt intelligence used in ARM B (experimental pipeline OFF-default
    posture: domain_aware=False), plus the always-on deterministic correction."""
    from sayit.core.asr.intelligence_pipeline import IntelligencePipeline
    return IntelligencePipeline(domain_aware=False)


def stage_timed_transcribe(backend: SherpaOnnxBackend, audio_i16, sr, pipe):
    """Replicate backend.transcribe but time preprocess vs decode separately,
    then time SayIt intelligence + deterministic formatting."""
    import sherpa_onnx  # noqa

    t0 = time.perf_counter()
    # --- preprocess (exact copy of backend semantics) ---
    if audio_i16.dtype == np.int16:
        audio_float = audio_i16.astype(np.float32) / 32768.0
    else:
        audio_float = audio_i16.astype(np.float32)
    if audio_float.ndim > 1:
        audio_float = audio_float[:, 0] if audio_float.shape[1] > 1 else audio_float.flatten()
    t1 = time.perf_counter()
    # --- ASR decode ---
    stream = backend._recognizer.create_stream()
    stream.accept_waveform(sr, audio_float)
    backend._recognizer.decode_stream(stream)
    raw = stream.result.text
    t2 = time.perf_counter()
    # --- SayIt intelligence (ARM B pipeline) ---
    intel = pipe.process(raw, "developer").text if pipe.available else raw
    t3 = time.perf_counter()
    # --- deterministic correction/formatting (always-on 6G/6I) ---
    final = correct_transcript(intel, enable_technical=True,
                               enable_formatting=True, enable_structured=True).text
    t4 = time.perf_counter()
    return {
        "preprocess_ms": (t1 - t0) * 1000.0,
        "asr_ms": (t2 - t1) * 1000.0,
        "intelligence_ms": (t3 - t2) * 1000.0,
        "formatting_ms": (t4 - t3) * 1000.0,
        "stop_to_final_ms": (t4 - t0) * 1000.0,
        "raw": raw,
        "final": final,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = _pipeline()

    # ---------- COLD vs WARM load ----------
    warm_cold = []
    base_rss = rss_mib()
    t0 = time.perf_counter()
    be = SherpaOnnxBackend()
    be.load(WHISPER)
    cold_load_s = time.perf_counter() - t0
    post_load_rss = rss_mib()
    warm_cold.append({"phase": "cold_load", "model": "whisper-small",
                      "load_s": round(cold_load_s, 3), "rss_mib": post_load_rss})

    # First (cold-cache) inference on the short clip, then repeated warm.
    d, sr = read_wav(BENCH["short"][0])
    first = stage_timed_transcribe(be, d, sr, pipe)
    warm_cold.append({"phase": "first_inference_short", "model": "whisper-small",
                      "load_s": round(first["stop_to_final_ms"] / 1000.0, 3),
                      "rss_mib": rss_mib()})
    warm_runs = [stage_timed_transcribe(be, d, sr, pipe)["stop_to_final_ms"] for _ in range(5)]
    warm_cold.append({"phase": "warm_inference_short_median", "model": "whisper-small",
                      "load_s": round(pctl(warm_runs, 0.5) / 1000.0, 3),
                      "rss_mib": rss_mib()})

    # ---------- Per-stage breakdown by utterance length (warm) ----------
    breakdown_rows = []
    REPS = 3
    for bucket, paths in BENCH.items():
        for p in paths:
            d, sr = read_wav(p)
            dur = len(d) / sr
            chunked = needs_chunking(d, sr)
            # warm reps (model already loaded)
            runs = [stage_timed_transcribe(be, d, sr, pipe) for _ in range(REPS)]
            for key in ("preprocess_ms", "asr_ms", "intelligence_ms", "formatting_ms", "stop_to_final_ms"):
                vals = [r[key] for r in runs]
                breakdown_rows.append({
                    "bucket": bucket, "clip": p.name, "duration_s": round(dur, 1),
                    "chunked": chunked, "stage": key,
                    "median_ms": round(pctl(vals, 0.5), 1),
                    "p95_ms": round(pctl(vals, 0.95), 1),
                })
            med_total = pctl([r["stop_to_final_ms"] for r in runs], 0.5)
            rtf = (med_total / 1000.0) / dur if dur > 0 else 0.0
            breakdown_rows.append({
                "bucket": bucket, "clip": p.name, "duration_s": round(dur, 1),
                "chunked": chunked, "stage": "RTF",
                "median_ms": round(rtf, 3), "p95_ms": round(rtf, 3),
            })

    be.unload(); gc.collect()

    # write
    with open(OUT / "warm_cold_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phase", "model", "load_s", "rss_mib"])
        w.writeheader(); w.writerows(warm_cold)
    with open(OUT / "latency_breakdown.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bucket", "clip", "duration_s", "chunked",
                                          "stage", "median_ms", "p95_ms"])
        w.writeheader(); w.writerows(breakdown_rows)

    # utterance-length summary (stop_to_final median + RTF per bucket)
    with open(OUT / "utterance_length_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "clip", "duration_s", "stop_to_final_median_ms", "RTF"])
        for r in breakdown_rows:
            if r["stage"] == "stop_to_final_ms":
                rtf = next(x["median_ms"] for x in breakdown_rows
                           if x["clip"] == r["clip"] and x["stage"] == "RTF")
                w.writerow([r["bucket"], r["clip"], r["duration_s"], r["median_ms"], rtf])

    print("base_rss_mib:", base_rss, "cold_load_s:", round(cold_load_s, 3))
    print("first_inference_short_ms:", round(first["stop_to_final_ms"], 1))
    print("warm_inference_short_median_ms:", round(pctl(warm_runs, 0.5), 1))
    print("--- per-stage median (ms) by clip ---")
    for r in breakdown_rows:
        if r["stage"] in ("asr_ms", "stop_to_final_ms"):
            print(f'{r["bucket"]:6s} {r["clip"]:18s} {r["duration_s"]:5.1f}s {r["stage"]:16s} med={r["median_ms"]:8.1f} p95={r["p95_ms"]:8.1f}')


if __name__ == "__main__":
    main()
