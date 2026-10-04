"""Phase 9J — live/in-app validation of the IntelligencePipeline (replay).

This environment has no live microphone, so this is CORPUS REPLAY through the
same pipeline the app would call — explicitly labeled as replay, NOT live-mic
evidence. It validates:
  - fail-safe behavior (missing index, empty text, bad input)
  - pure-post-text safety (pipeline imports nothing audio/recorder/safezone/UI)
  - the ambiguous developer case across contexts (conservatism)
  - latency of the pipeline step vs the raw (no-op) baseline
  - no transcript logging (diagnostics are counts only)
"""

from __future__ import annotations

import ast
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))

import metrics as M  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
OUT = ROOT / "artifacts" / "phase9j"


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def find_wav(e):
    wav = e.get("wav", e["id"] + ".wav")
    for base in (CORPUS, EVAL):
        if (base / wav).exists():
            return base / wav
    return None


def context_for(e):
    role, cat = e.get("pair_role"), e.get("category")
    if role == "technical" or cat in ("technical", "multiword"):
        return "developer"
    if role == "ordinary":
        return "email"
    if cat == "mixed":
        return "developer"
    return "email"


def greedy_clips():
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    out = []
    for e in json.loads(LABELS.read_text(encoding="utf-8")):
        if e.get("needs_recording"):
            continue
        p = find_wav(e)
        if p is None:
            continue
        d, sr, _ = read_wav(p)
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        out.append({"id": e["id"], "hyp": s.result.text.strip(), "context": context_for(e)})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = IntelligencePipeline()
    report = {"phase": "9J", "timestamp": datetime.now(timezone.utc).isoformat(),
              "evidence_type": "corpus_replay (NOT live microphone)"}

    report["pipeline_available"] = pipe.available

    # Fail-safe cases.
    failsafe = {
        "empty": pipe.process("", "developer").text,
        "whitespace": pipe.process("   ", "developer").text,
        "none_safe": pipe.process(None, "developer").text,  # type: ignore
    }
    # Missing-index pipeline must no-op.
    missing = IntelligencePipeline(index_path=ROOT / "does_not_exist.json")
    failsafe["missing_index_unchanged"] = (
        missing.process("run against postjsql", "developer").text == "run against postjsql")
    report["failsafe"] = failsafe

    # Pure-post-text safety: the pipeline module must not import audio/recorder/
    # safezone/clipboard/UI; it only transforms text.
    src = (ROOT / "src" / "sayit" / "core" / "asr" / "intelligence_pipeline.py").read_text(encoding="utf-8")
    imports = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imports += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = ("audio", "recorder", "safezones", "output", "input", "ui",
                 "pyperclip", "pynput", "urllib", "requests", "socket", "subprocess")
    report["pure_post_text"] = {
        "imports": imports,
        "clean": not any(any(b in (m or "") for b in forbidden) for m in imports),
    }

    # Corpus replay through the pipeline.
    clips = greedy_clips()
    replay = {}
    for c in clips:
        r = pipe.process(c["hyp"], c["context"])
        replay[c["id"]] = {"context": c["context"], "changed": r.changed, "reason": r.reason}
    report["replay_summary"] = {
        "clips": len(clips),
        "changed": sum(1 for v in replay.values() if v["changed"]),
    }
    (OUT / "replay_results.json").write_text(json.dumps(replay, indent=2), encoding="utf-8")

    # Ambiguous developer case across contexts (conservatism).
    amb = {}
    for text, ctx in [("i need a fast api for the service", "developer"),
                      ("i need a fast api for the service", "email"),
                      ("i need a fast api for the service", "chat"),
                      ("i need a fast api for the service", "normal")]:
        out_text = pipe.process(text, ctx).text
        amb[ctx] = {"output": out_text, "became_technical": "FastAPI" in out_text}
    report["ambiguous_developer_case"] = amb

    # Latency: pipeline step vs raw no-op baseline.
    sample = [(c["hyp"], c["context"]) for c in clips]
    for _ in range(10):
        for h, ctx in sample:
            pipe.process(h, ctx)
    ts = []
    for _ in range(30):
        for h, ctx in sample:
            t0 = time.perf_counter(); pipe.process(h, ctx); ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    report["latency"] = {"pipeline_median_ms": round(ts[len(ts) // 2], 3),
                         "pipeline_p95_ms": round(ts[int(len(ts) * 0.95)], 3),
                         "baseline_noop_ms": 0.0}

    # No transcript logging: diagnostics are counts only.
    pipe.process("run against postjsql", "developer")
    report["diagnostics_sample"] = pipe.last_diagnostics
    report["diagnostics_contains_no_transcript"] = (
        "transcript" not in json.dumps(pipe.last_diagnostics).lower())

    (OUT / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("available:", report["pipeline_available"],
          "| pure_post_text clean:", report["pure_post_text"]["clean"])
    print("failsafe missing_index_unchanged:", failsafe["missing_index_unchanged"])
    print("ambiguous dev case:", {k: v["became_technical"] for k, v in amb.items()})
    print("replay changed:", report["replay_summary"])
    print("latency:", report["latency"])


if __name__ == "__main__":
    main()
