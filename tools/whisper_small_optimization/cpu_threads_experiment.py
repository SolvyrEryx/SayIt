"""Bounded CPU-threading experiment for Whisper Small (production FROZEN).

Measures a SMALL set of num_threads values on a fixed dev benchmark, using the
SAME from_whisper construction + greedy decoding as production (backends.py),
only varying num_threads. Verifies the transcript is byte-identical so we never
trade accuracy for speed. Nothing in production is modified; this is isolated.

sherpa-onnx's from_whisper exposes a single num_threads (ORT intra-op). There is
no separate inter-op knob in this API surface, so the bounded set is the thread
count. Provider stays "cpu" (the installed build is CPU-only).
"""
from __future__ import annotations

import csv
import gc
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.asr import speech_mode as SM  # noqa: E402
from sayit.core.asr.file_utils import (  # noqa: E402
    find_file_by_suffix, get_models_dir,
)

OUT = ROOT / "artifacts" / "whisper_small_optimization"
MODEL_DIR = Path(get_models_dir()) / SM.HIGHER_ACCURACY_MODEL_ID
THREADS = [1, 2, 4, 6, 8, 12]           # 4 = current production value
CLIPS = {
    "short_A": ROOT / "artifacts/phase6/eval-audio/A.wav",     # 4.7s
    "medium_E": ROOT / "artifacts/phase6/eval-audio/E.wav",    # 8.6s
    "long_F": ROOT / "artifacts/phase6/eval-audio/F.wav",      # 16.4s
}
REPS = 4


def read_wav(p):
    w = wave.open(str(p), "rb"); sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    w.close(); return d, sr


def rss_mib():
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / 1048576, 1)
    except Exception:
        return None


def pctl(xs, q):
    s = sorted(xs); i = max(0, min(len(s) - 1, int(round((len(s) - 1) * q)))); return s[i]


def build(num_threads):
    import sherpa_onnx
    encoder = find_file_by_suffix(str(MODEL_DIR), "-encoder.onnx", "-encoder.int8.onnx")
    decoder = find_file_by_suffix(str(MODEL_DIR), "-decoder.onnx", "-decoder.int8.onnx")
    tokens = find_file_by_suffix(str(MODEL_DIR), "-tokens", "tokens.txt")
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=encoder, decoder=decoder, tokens=tokens,
        num_threads=num_threads, provider="cpu", debug=False,
        decoding_method="greedy_search",
    )


def transcribe(rec, audio, sr):
    s = rec.create_stream(); s.accept_waveform(sr, audio); rec.decode_stream(s)
    return s.result.text


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = {k: read_wav(p) for k, p in CLIPS.items()}
    ref_text = {}
    rows = []
    for nt in THREADS:
        rec = build(nt)
        load_rss = rss_mib()
        for cname, (d, sr) in clips.items():
            dur = len(d) / sr
            # warm it once, then measure
            txt = transcribe(rec, d, sr)
            runs = []
            for _ in range(REPS):
                t0 = time.perf_counter(); t = transcribe(rec, d, sr)
                runs.append((time.perf_counter() - t0) * 1000.0)
            ref_text.setdefault(cname, txt)
            identical = (t == ref_text[cname])
            med = pctl(runs, 0.5)
            rows.append({
                "num_threads": nt, "clip": cname, "duration_s": round(dur, 1),
                "median_ms": round(med, 1), "p95_ms": round(pctl(runs, 0.95), 1),
                "rtf": round((med / 1000.0) / dur, 3),
                "rss_mib": load_rss, "transcript_identical_to_4thread": identical,
            })
        del rec; gc.collect()

    with open(OUT / "cpu_configurations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["num_threads", "clip", "duration_s",
                                          "median_ms", "p95_ms", "rtf", "rss_mib",
                                          "transcript_identical_to_4thread"])
        w.writeheader(); w.writerows(rows)

    # Console summary: median per thread count, aggregated over clips (mean).
    print("num_threads | medium_E med_ms | long_F med_ms | all identical?")
    for nt in THREADS:
        me = next(r["median_ms"] for r in rows if r["num_threads"] == nt and r["clip"] == "medium_E")
        lf = next(r["median_ms"] for r in rows if r["num_threads"] == nt and r["clip"] == "long_F")
        ident = all(r["transcript_identical_to_4thread"] for r in rows if r["num_threads"] == nt)
        marker = "  <= current" if nt == 4 else ""
        print(f"   {nt:4d}     | {me:12.1f}   | {lf:11.1f}   | {ident}{marker}")


if __name__ == "__main__":
    main()
