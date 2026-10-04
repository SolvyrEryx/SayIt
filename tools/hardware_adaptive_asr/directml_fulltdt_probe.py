"""ISOLATED DirectML full-graph-set feasibility probe (Phase 11/17).

Extends the encoder-only probe: tries to CREATE DirectML sessions for ALL THREE
Parakeet TDT graphs (encoder, decoder/predictor, joiner) and run one forward on
each with synthetic, shape-matched inputs. This tells us whether a custom
sherpa-onnx-DirectML build could even host the whole model, WITHOUT claiming
transcript parity (the TDT greedy decode loop is sherpa C++ and is not
reimplemented here).

Honest about scope: creating + running each graph on DML != byte-identical
end-to-end transcription. Writes directml_fulltdt_probe.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

MDIR = Path.home() / "AppData/Local/SayIt/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
OUT = Path(__file__).resolve().parents[2] / "artifacts" / "hardware_adaptive_asr"
GRAPHS = {
    "encoder": MDIR / "encoder.int8.onnx",
    "decoder": MDIR / "decoder.int8.onnx",
    "joiner": MDIR / "joiner.int8.onnx",
}


def io_desc(sess):
    return (
        [{"name": i.name, "shape": [str(s) for s in i.shape], "type": i.type} for i in sess.get_inputs()],
        [{"name": o.name, "shape": [str(s) for s in o.shape], "type": o.type} for o in sess.get_outputs()],
    )


def synth(sess, time_frames=200):
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
        nm = (i.name or "").lower()
        if "int" in i.type:
            feeds[i.name] = (np.full(shape, time_frames, dtype=np.int64) if "len" in nm
                             else np.zeros(shape, dtype=np.int64))
        elif "float16" in i.type:
            feeds[i.name] = np.random.randn(*shape).astype(np.float16)
        else:
            feeds[i.name] = np.random.randn(*shape).astype(np.float32)
    return feeds


def probe(path, provider):
    r = {"provider": provider}
    try:
        sess = ort.InferenceSession(str(path), providers=[provider, "CPUExecutionProvider"])
        r["session_providers"] = sess.get_providers()
        ins, outs = io_desc(sess)
        r["n_inputs"], r["n_outputs"] = len(ins), len(outs)
        feeds = synth(sess)
        t0 = time.perf_counter()
        sess.run(None, feeds)
        r["ran_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        r["ok"] = True
    except Exception as e:
        r["ok"] = False
        r["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "ort_version": ort.__version__,
        "available_providers": ort.get_available_providers(),
        "scope_note": ("Creates + runs each Parakeet graph on DirectML with synthetic inputs. "
                       "Does NOT perform the TDT greedy decode or assert transcript parity."),
        "graphs": {},
    }
    for name, path in GRAPHS.items():
        report["graphs"][name] = {
            "exists": path.exists(),
            "cpu": probe(path, "CPUExecutionProvider") if path.exists() else {"ok": False, "error": "missing"},
            "directml": probe(path, "DmlExecutionProvider") if path.exists() else {"ok": False, "error": "missing"},
        }
    all_dml_ok = all(g["directml"].get("ok") for g in report["graphs"].values())
    report["all_three_graphs_load_and_run_on_directml"] = all_dml_ok
    (OUT / "directml_fulltdt_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "all_three_graphs_run_on_dml": all_dml_ok,
        **{n: {"cpu_ok": g["cpu"].get("ok"), "dml_ok": g["directml"].get("ok"),
               "dml_err": g["directml"].get("error")} for n, g in report["graphs"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()
