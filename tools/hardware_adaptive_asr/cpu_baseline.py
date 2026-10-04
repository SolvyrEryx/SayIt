"""CPU baseline benchmark for the hardware-adaptive ASR investigation.

Uses the PRODUCTION SherpaOnnxBackend (sherpa-onnx 1.12.21, CPU-only ORT) with
the shipped Parakeet TDT 0.6B v2 int8 model, exactly as SayIt runs it. Measures
real stop-to-ASR latency per clip (cold load + warm medians), RTF, RSS, and
records the transcript so a later GPU experiment can be compared for parity.

Read-only: imports the production package, loads the real model, times it.
Does NOT modify production code or the environment. Writes JSON/CSV artifacts.
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

from sayit.core.asr.backends import SherpaOnnxBackend  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
OUT = ROOT / "artifacts" / "hardware_adaptive_asr"
CLIPS = {
    "A": ROOT / "artifacts/phase6/eval-audio/A.wav",
    "B": ROOT / "artifacts/phase6/eval-audio/B.wav",
    "C": ROOT / "artifacts/phase6/eval-audio/C.wav",
    "D": ROOT / "artifacts/phase6/eval-audio/D.wav",
    "E": ROOT / "artifacts/phase6/eval-audio/E.wav",
    "F": ROOT / "artifacts/phase6/eval-audio/F.wav",
}
REPS = 5


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
    s = sorted(xs)
    i = max(0, min(len(s) - 1, int(round((len(s) - 1) * q))))
    return s[i]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    model_dir = os.path.join(get_models_dir(), MODEL_ID)

    base_rss = rss_mib()
    t0 = time.perf_counter()
    be = SherpaOnnxBackend()
    be.load(MODEL_ID)
    cold_load_s = time.perf_counter() - t0
    post_load_rss = rss_mib()

    rows = []
    transcripts = {}
    for name, path in CLIPS.items():
        d, sr = read_wav(path)
        dur = len(d) / sr
        # warm once
        r = be.transcribe(d, sr)
        transcripts[name] = r.text
        runs = []
        for _ in range(REPS):
            t = time.perf_counter()
            be.transcribe(d, sr)
            runs.append((time.perf_counter() - t) * 1000.0)
        med = pctl(runs, 0.5)
        rows.append({
            "clip": name, "duration_s": round(dur, 2),
            "p50_ms": round(med, 1), "p95_ms": round(pctl(runs, 0.95), 1),
            "rtf": round((med / 1000.0) / dur, 3),
        })

    be.unload(); gc.collect()
    post_unload_rss = rss_mib()

    summary = {
        "backend": "CPU (sherpa-onnx 1.12.21 bundled ORT)",
        "model": MODEL_ID,
        "device": "AMD Ryzen 5 4600G 6c/12t",
        "cold_load_s": round(cold_load_s, 3),
        "base_rss_mib": base_rss,
        "post_load_rss_mib": post_load_rss,
        "post_unload_rss_mib": post_unload_rss,
        "clips": rows,
    }
    (OUT / "cpu_baseline.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "cpu_transcripts.json").write_text(json.dumps(transcripts, indent=2), encoding="utf-8")
    with open(OUT / "cpu_baseline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["clip", "duration_s", "p50_ms", "p95_ms", "rtf"])
        w.writeheader(); w.writerows(rows)

    print("cold_load_s:", round(cold_load_s, 3), "| base_rss:", base_rss,
          "| post_load_rss:", post_load_rss, "| post_unload_rss:", post_unload_rss)
    for r in rows:
        print(f'  {r["clip"]} dur={r["duration_s"]:5.2f}s p50={r["p50_ms"]:7.1f}ms '
              f'p95={r["p95_ms"]:7.1f}ms rtf={r["rtf"]}')


if __name__ == "__main__":
    main()
