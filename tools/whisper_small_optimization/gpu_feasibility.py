"""GPU feasibility isolation experiment for Whisper Small (production FROZEN).

Does NOT modify production. Attempts to construct the SAME from_whisper
recognizer with provider="cuda" vs provider="cpu" and compares warm decode
timing, while sampling nvidia-smi for GPU utilization + VRAM during the CUDA
decode. If the installed sherpa-onnx is a CPU-only build (no CUDA provider
DLLs), ORT silently falls back to CPU: we detect this because (a) timing is
indistinguishable from CPU and (b) GPU utilization stays ~idle during decode.

No new dependency is installed. This only probes what the existing environment
can do.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.asr import speech_mode as SM  # noqa: E402
from sayit.core.asr.file_utils import find_file_by_suffix, get_models_dir  # noqa: E402

MODEL_DIR = Path(get_models_dir()) / SM.HIGHER_ACCURACY_MODEL_ID
CLIP = ROOT / "artifacts/phase6/eval-audio/F.wav"  # 16.4s long clip


def read_wav(p):
    w = wave.open(str(p), "rb"); sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    w.close(); return d, sr


def build(provider):
    import sherpa_onnx
    enc = find_file_by_suffix(str(MODEL_DIR), "-encoder.onnx", "-encoder.int8.onnx")
    dec = find_file_by_suffix(str(MODEL_DIR), "-decoder.onnx", "-decoder.int8.onnx")
    tok = find_file_by_suffix(str(MODEL_DIR), "-tokens", "tokens.txt")
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=enc, decoder=dec, tokens=tok, num_threads=4,
        provider=provider, debug=False, decoding_method="greedy_search")


def gpu_sample():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        u, m = out.stdout.strip().splitlines()[0].split(",")
        return int(u.strip()), int(m.strip())
    except Exception:
        return None, None


def timed_decode_with_gpu_watch(rec, audio, sr, label):
    samples = []
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            u, m = gpu_sample()
            if u is not None:
                samples.append((u, m))
            time.sleep(0.2)

    th = threading.Thread(target=watch, daemon=True); th.start()
    # warm
    s = rec.create_stream(); s.accept_waveform(sr, audio); rec.decode_stream(s)
    t0 = time.perf_counter()
    for _ in range(3):
        s = rec.create_stream(); s.accept_waveform(sr, audio); rec.decode_stream(s)
    dt = (time.perf_counter() - t0) / 3 * 1000.0
    stop.set(); th.join(timeout=2)
    peak_util = max((u for u, _ in samples), default=None)
    peak_mem = max((m for _, m in samples), default=None)
    return {"provider": label, "median_decode_ms": round(dt, 1),
            "peak_gpu_util_pct": peak_util, "peak_vram_used_mib": peak_mem,
            "text": s.result.text[:60]}


def main():
    d, sr = read_wav(CLIP)
    results = {}
    idle_u, idle_m = gpu_sample()
    results["gpu_idle"] = {"util_pct": idle_u, "vram_used_mib": idle_m}

    for prov in ("cpu", "cuda"):
        try:
            rec = build(prov)
            results[prov] = timed_decode_with_gpu_watch(rec, d, sr, prov)
            del rec
        except Exception as e:
            results[prov] = {"provider": prov, "error": repr(e)}

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
