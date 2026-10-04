"""Verify ACTUAL GPU execution of the DML encoder run via nvidia-smi sampling.

Runs many encoder forwards on DmlExecutionProvider in a loop while sampling
`nvidia-smi --query-gpu=utilization.gpu,memory.used` so we can confirm real GPU
activity (not a silent CPU fallback). Isolated env only.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

MODEL = Path.home() / "AppData/Local/SayIt/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/encoder.int8.onnx"
OUT = Path(__file__).resolve().parents[2] / "artifacts" / "hardware_adaptive_asr"

samples = []
stop = threading.Event()


def sample_smi():
    while not stop.is_set():
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            line = r.stdout.strip().splitlines()[0]
            util, mem = [x.strip() for x in line.split(",")]
            samples.append({"t": round(time.time(), 2), "gpu_util_pct": int(util), "mem_used_mib": int(mem)})
        except Exception:
            pass
        time.sleep(0.2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sess = ort.InferenceSession(str(MODEL), providers=["DmlExecutionProvider", "CPUExecutionProvider"])
    feeds = {}
    for i in sess.get_inputs():
        shape = []
        for s in i.shape:
            shape.append(s if isinstance(s, int) and s > 0 else (1 if not shape else (500 if len(shape) == 1 else 80)))
        nm = (i.name or "").lower()
        if "int64" in i.type:
            feeds[i.name] = np.full(shape, 500, np.int64) if "len" in nm else np.zeros(shape, np.int64)
        else:
            feeds[i.name] = np.random.randn(*shape).astype(np.float32 if "float16" not in i.type else np.float16)

    # baseline GPU util
    base = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True).stdout.strip().splitlines()[0]

    th = threading.Thread(target=sample_smi, daemon=True)
    th.start()
    sess.run(None, feeds)  # warm
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < 6.0:
        sess.run(None, feeds)
        n += 1
    stop.set(); th.join(timeout=2)

    peak_util = max((s["gpu_util_pct"] for s in samples), default=None)
    peak_mem = max((s["mem_used_mib"] for s in samples), default=None)
    report = {
        "baseline_smi": base,
        "iterations_in_6s": n,
        "providers_in_session": sess.get_providers(),
        "peak_gpu_util_pct": peak_util,
        "peak_mem_used_mib": peak_mem,
        "n_samples": len(samples),
        "verdict": ("GPU ACTIVITY OBSERVED" if (peak_util or 0) > 5 else "NO clear GPU activity (possible CPU fallback)"),
    }
    (OUT / "directml_gpu_verify.json").write_text(json.dumps({"report": report, "samples": samples}, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
