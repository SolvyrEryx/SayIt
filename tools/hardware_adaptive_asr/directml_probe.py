"""ISOLATED DirectML feasibility probe for the Parakeet int8 ENCODER graph.

Runs ONLY in the throwaway gpu_probe_env (onnxruntime-directml). It does NOT use
sherpa-onnx and does NOT touch the production env. Purpose: answer the bounded
question "can a DX12 GPU EP (DirectML) load and execute SayIt's Parakeet int8
encoder ONNX graph on this machine, and does it run without fatal operator
errors?" — NOT to produce a transcript (full TDT decode is not reimplemented).

Verifies:
- encoder session creates on DmlExecutionProvider (not silently CPU-only)
- which EP ORT actually assigns
- a single encoder forward runs (or records the exact failure)
- CPU-vs-DML wall time on identical synthetic input
Writes artifacts/hardware_adaptive_asr/directml_probe.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

MODEL = Path.home() / "AppData/Local/SayIt/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/encoder.int8.onnx"
OUT = Path(__file__).resolve().parents[2] / "artifacts" / "hardware_adaptive_asr"


def describe_io(sess):
    ins = [{"name": i.name, "shape": [str(s) for s in i.shape], "type": i.type} for i in sess.get_inputs()]
    outs = [{"name": o.name, "shape": [str(s) for s in o.shape], "type": o.type} for o in sess.get_outputs()]
    return ins, outs


def synth_inputs(sess, n_frames=500):
    """Build plausible encoder inputs from the graph's declared shapes.
    Parakeet FastConformer encoder typically takes (audio features [B, T, D]) and
    a lengths vector. We fill dynamic dims with concrete sizes and dtype-match.
    """
    feeds = {}
    for i in sess.get_inputs():
        shape = []
        for s in i.shape:
            if isinstance(s, int) and s > 0:
                shape.append(s)
            else:
                # dynamic: batch=1, time=n_frames, feature=80 heuristics
                nm = (i.name or "").lower()
                if "length" in nm or "len" in nm:
                    shape.append(1)
                elif not shape:
                    shape.append(1)
                elif len(shape) == 1:
                    shape.append(n_frames)
                else:
                    shape.append(80)
        t = i.type
        if "int64" in t:
            arr = np.full(shape, n_frames, dtype=np.int64) if ("len" in (i.name or "").lower()) else np.zeros(shape, np.int64)
        elif "float16" in t:
            arr = np.random.randn(*shape).astype(np.float16)
        else:
            arr = np.random.randn(*shape).astype(np.float32)
        feeds[i.name] = arr
    return feeds


def run_ep(provider):
    res = {"provider_requested": provider}
    try:
        so = ort.SessionOptions()
        sess = ort.InferenceSession(str(MODEL), sess_options=so, providers=[provider, "CPUExecutionProvider"])
        res["providers_in_session"] = sess.get_providers()
        ins, outs = describe_io(sess)
        res["inputs"], res["outputs"] = ins, outs
        feeds = synth_inputs(sess)
        # warm + time
        t0 = time.perf_counter()
        out = sess.run(None, feeds)
        res["first_run_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        runs = []
        for _ in range(5):
            t = time.perf_counter()
            sess.run(None, feeds)
            runs.append((time.perf_counter() - t) * 1000.0)
        runs.sort()
        res["warm_median_ms"] = round(runs[len(runs) // 2], 1)
        res["output_count"] = len(out)
        res["ok"] = True
    except Exception as e:
        res["ok"] = False
        res["error"] = f"{type(e).__name__}: {e}"
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "ort_version": ort.__version__,
        "available_providers": ort.get_available_providers(),
        "model": str(MODEL),
        "model_exists": MODEL.exists(),
        "note": "Encoder-only graph execution probe. Full TDT transcript parity NOT evaluated here.",
        "cpu": run_ep("CPUExecutionProvider"),
        "directml": run_ep("DmlExecutionProvider"),
    }
    (OUT / "directml_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk in ("ok", "error", "providers_in_session", "first_run_ms", "warm_median_ms")}) for k, v in report.items() if k in ("ort_version", "available_providers", "model_exists", "cpu", "directml")}, indent=2))


if __name__ == "__main__":
    main()
