"""ISOLATED DirectML probe v2 (Phase 3, RULE 6/7): dtype-correct.

Builds each graph's synthetic inputs STRICTLY from the declared ONNX input type
(int32 vs int64 vs float32/float16), fixing the earlier probe artifact where the
decoder got int64 token ids but expects int32. Confirms whether encoder,
decoder, and joiner all CREATE + RUN on DmlExecutionProvider.

Scope honesty: this proves per-graph execution on the DX12 GPU EP. It does NOT
run the token-and-duration greedy TDT decode loop (that lives in sherpa-onnx
C++), so it does NOT assert end-to-end transcript parity. Isolated env only;
production untouched. Writes directml_probe_v2.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

MDIR = Path.home() / "AppData/Local/SayIt/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
OUT = Path(__file__).resolve().parents[2] / "artifacts" / "phase3"
GRAPHS = {"encoder": MDIR / "encoder.int8.onnx",
          "decoder": MDIR / "decoder.int8.onnx",
          "joiner": MDIR / "joiner.int8.onnx"}


def _dtype_for(t: str):
    if "int64" in t:
        return np.int64
    if "int32" in t:
        return np.int32
    if "float16" in t:
        return np.float16
    return np.float32


def synth(sess, time_frames=120):
    feeds = {}
    for i in sess.get_inputs():
        shape = []
        for s in i.shape:
            if isinstance(s, int) and s > 0:
                shape.append(s)
            else:
                nm = (i.name or "").lower()
                if "len" in nm:
                    shape.append(1)
                elif not shape:
                    shape.append(1)
                elif len(shape) == 1:
                    shape.append(time_frames)
                else:
                    shape.append(80)
        dt = _dtype_for(i.type)
        nm = (i.name or "").lower()
        if dt in (np.int64, np.int32):
            # lengths get the frame count; token/state ids get 0 (valid index)
            feeds[i.name] = (np.full(shape, time_frames, dtype=dt) if "len" in nm
                             else np.zeros(shape, dtype=dt))
        else:
            feeds[i.name] = np.random.randn(*shape).astype(dt)
    return feeds


def probe(path, provider):
    r = {"provider": provider}
    try:
        sess = ort.InferenceSession(str(path), providers=[provider, "CPUExecutionProvider"])
        r["session_providers"] = sess.get_providers()
        r["input_types"] = {i.name: i.type for i in sess.get_inputs()}
        sess.run(None, synth(sess))
        r["ok"] = True
    except Exception as e:
        r["ok"] = False
        r["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"ort_version": ort.__version__,
              "available_providers": ort.get_available_providers(),
              "scope": ("Per-graph CREATE+RUN on DirectML with dtype-correct synthetic inputs. "
                        "NOT an end-to-end TDT decode; no transcript parity claim."),
              "graphs": {}}
    for name, path in GRAPHS.items():
        report["graphs"][name] = {
            "exists": path.exists(),
            "cpu": probe(path, "CPUExecutionProvider") if path.exists() else {"ok": False, "error": "missing"},
            "directml": probe(path, "DmlExecutionProvider") if path.exists() else {"ok": False, "error": "missing"},
        }
    report["all_three_run_on_directml"] = all(g["directml"].get("ok") for g in report["graphs"].values())
    report["all_three_run_on_cpu"] = all(g["cpu"].get("ok") for g in report["graphs"].values())
    (OUT / "directml_probe_v2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "all_three_run_on_directml": report["all_three_run_on_directml"],
        "all_three_run_on_cpu": report["all_three_run_on_cpu"],
        **{n: {"cpu": g["cpu"].get("ok"), "dml": g["directml"].get("ok"),
               "dml_err": g["directml"].get("error")} for n, g in report["graphs"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()
