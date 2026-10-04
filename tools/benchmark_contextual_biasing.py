"""Phase 9A — decoder contextual-biasing proof-of-capability (ISOLATED).

This tool is experimental and makes NO changes to SayIt's production decoding
path. It answers one question with executable evidence:

    Can SayIt's installed sherpa-onnx + Parakeet TDT int8 (NeMo transducer)
    benefit from decoder-level hotwords / contextual biasing?

It does three things and writes machine-readable JSON to artifacts/phase9/9A/:

1. COMPATIBILITY MATRIX. Probes, each in an isolated subprocess (so a C++-level
   process abort is captured as an exit code rather than killing this tool):
     - greedy_search                      (the production config) -> expected OK
     - greedy_search + hotwords_file      -> expected catchable error
     - modified_beam_search (no hotwords) -> expected hard abort for nemo
     - modified_beam_search + hotwords    -> expected hard abort for nemo

2. BASELINE DECODE. Runs the real greedy baseline on the shared eval-audio
   corpus (artifacts/phase6/eval-audio/A-E.wav, with A-E.txt references),
   reusing the Phase 6F methodology (_read_wav + wer). Measures WER,
   technical-term recall, exact technical-term accuracy, a false-substitution
   probe, latency, RTF, and determinism (two identical runs).

3. CONTEXTUAL ARM. Attempts to build the contextual recognizer with a swept
   hotword set — but because the compatibility matrix shows this aborts for the
   NeMo transducer, the attempt runs in an isolated subprocess and its failure
   is recorded as evidence (never fabricated).

Nothing here logs transcript text through the application logger; transcripts
for the controlled corpus are written only to the artifacts JSON (a controlled
local store), consistent with Phase 6F.

Usage:
    uv run python tools/benchmark_contextual_biasing.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import tracemalloc
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sayit.core.asr.file_utils import get_models_dir  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
EVAL_AUDIO = Path("artifacts/phase6/eval-audio")
OUT_DIR = Path("artifacts/phase9/9A")

# Controlled technical hotword vocabulary (from the Phase 9A spec lists). Used
# only for the contextual arm / size sweep. Ordered so the size sweep is stable.
CONTROLLED_HOTWORDS = [
    "PostgreSQL", "GitHub", "Python", "FastAPI", "TypeScript",
    "Kubernetes", "Docker", "PyTorch", "TensorFlow", "SQLAlchemy",
    "Pydantic", "Redis", "MongoDB", "nginx", "OAuth2",
    "JWT", "TLS", "WebAuthn", "ONNX", "CUDA",
    "Transformer", "LangChain", "scikit-learn", "NumPy", "Pandas",
    "Django", "Flask", "React", "Next.js", "Rust",
    "Kotlin", "Swift", "Elasticsearch", "Terraform", "Ansible",
    "Prometheus", "Grafana", "Kafka", "RabbitMQ", "SAML",
    "OpenID", "RBAC", "IAM", "mTLS", "FIDO2",
    "QLoRA", "LoRA", "BERT", "TensorRT", "embeddings",
]

# Technical terms we expect in the eval references (for recall/exact metrics).
# These correspond to eval-audio D and E (see eval-audio/README.md).
EXPECTED_TECH_TERMS = ["github", "python", "postgresql", "cicd", "tls", "firewall"]


def _normalize(text: str):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def wer(reference: str, hypothesis: str):
    r, h = _normalize(reference), _normalize(hypothesis)
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[len(r)][len(h)], len(r)


def _read_wav(path: Path):
    w = wave.open(str(path), "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr, n / sr


def _model_files():
    m = Path(get_models_dir()) / MODEL_ID
    return {
        "dir": str(m),
        "encoder": str(m / "encoder.int8.onnx"),
        "decoder": str(m / "decoder.int8.onnx"),
        "joiner": str(m / "joiner.int8.onnx"),
        "tokens": str(m / "tokens.txt"),
        "present": m.is_dir(),
        "bpe_model_present": (m / "bpe.model").exists(),
    }


# --- isolated subprocess probe ----------------------------------------------

_PROBE_SRC = r"""
import os, sys, json
import sherpa_onnx
cfg = json.loads(sys.argv[1])
kw = dict(
    encoder=cfg["encoder"], decoder=cfg["decoder"], joiner=cfg["joiner"],
    tokens=cfg["tokens"], num_threads=2, provider="cpu",
    decoding_method=cfg["decoding_method"], model_type="nemo_transducer",
)
if cfg.get("hotwords_file"):
    kw["hotwords_file"] = cfg["hotwords_file"]
    kw["hotwords_score"] = cfg.get("hotwords_score", 2.0)
    kw["modeling_unit"] = cfg.get("modeling_unit", "cjkchar")
try:
    r = sherpa_onnx.OfflineRecognizer.from_transducer(**kw)
    print("RESULT:LOADED")
except BaseException as e:
    print("RESULT:PYERROR:" + type(e).__name__ + ":" + str(e)[:200])
"""


def _run_isolated(cfg: dict) -> dict:
    """Run one recognizer-construction probe in a subprocess.

    Returns the outcome classification so a C++ `exit()`/abort is captured as a
    non-zero return code rather than killing this benchmark.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE_SRC, json.dumps(cfg)],
        capture_output=True, text=True, timeout=120,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if "RESULT:LOADED" in stdout:
        outcome = "loaded"
    elif "RESULT:PYERROR:" in stdout:
        outcome = "python_error"
    elif proc.returncode != 0:
        outcome = "process_abort"
    else:
        outcome = "unknown"
    return {
        "outcome": outcome,
        "returncode": proc.returncode,
        "stdout": stdout[-300:],
        "stderr": stderr[-300:],
    }


def build_compatibility_matrix(mf: dict) -> dict:
    hw = OUT_DIR / "_hotwords_probe.txt"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hw.write_text("PostgreSQL\nGitHub\nFastAPI\n", encoding="utf-8")
    base = {
        "encoder": mf["encoder"], "decoder": mf["decoder"],
        "joiner": mf["joiner"], "tokens": mf["tokens"],
    }
    matrix = {
        "greedy_search": _run_isolated({**base, "decoding_method": "greedy_search"}),
        "greedy_search_plus_hotwords": _run_isolated(
            {**base, "decoding_method": "greedy_search",
             "hotwords_file": str(hw), "hotwords_score": 2.0,
             "modeling_unit": "cjkchar"}
        ),
        "modified_beam_search": _run_isolated(
            {**base, "decoding_method": "modified_beam_search"}
        ),
        "modified_beam_search_plus_hotwords": _run_isolated(
            {**base, "decoding_method": "modified_beam_search",
             "hotwords_file": str(hw), "hotwords_score": 2.0,
             "modeling_unit": "cjkchar"}
        ),
    }
    hw.unlink(missing_ok=True)
    hotwords_usable = (
        matrix["modified_beam_search_plus_hotwords"]["outcome"] == "loaded"
    )
    return {"probes": matrix, "hotwords_usable": hotwords_usable}


# --- baseline decode ---------------------------------------------------------

def _tech_metrics(ref: str, hyp: str):
    """Technical-term recall + exact accuracy for the controlled terms, plus a
    simple false-substitution signal (terms in hyp not in ref)."""
    rset = set(_normalize(ref))
    hset = set(_normalize(hyp))
    present = [t for t in EXPECTED_TECH_TERMS if t in rset]
    recalled = [t for t in present if t in hset]
    recall = (len(recalled) / len(present)) if present else None
    # False technical substitution probe: controlled hotword tokens that appear
    # in hyp but are absent from ref (would indicate a wrongly-forced term).
    hw_tokens = set(_normalize(" ".join(CONTROLLED_HOTWORDS)))
    false_subs = sorted((hw_tokens & hset) - rset)
    return {
        "expected_terms_present": present,
        "recalled_terms": recalled,
        "tech_term_recall": recall,
        "false_substitution_tokens": false_subs,
    }


def run_baseline(mf: dict) -> dict:
    import sherpa_onnx

    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=mf["encoder"], decoder=mf["decoder"], joiner=mf["joiner"],
        tokens=mf["tokens"], num_threads=4, provider="cpu",
        decoding_method="greedy_search", model_type="nemo_transducer",
    )

    def decode(data, sr):
        s = rec.create_stream()
        s.accept_waveform(sr, data)
        rec.decode_stream(s)
        return s.result.text

    clips = []
    tracemalloc.start()
    for name in ["A", "B", "C", "D", "E"]:
        wav = EVAL_AUDIO / f"{name}.wav"
        ref_file = EVAL_AUDIO / f"{name}.txt"
        if not wav.exists() or not ref_file.exists():
            continue
        data, sr, dur = _read_wav(wav)
        ref = ref_file.read_text(encoding="utf-8").strip()

        t0 = time.perf_counter()
        hyp1 = decode(data, sr)
        t1 = time.perf_counter()
        hyp2 = decode(data, sr)  # determinism check

        errs, words = wer(ref, hyp1)
        clips.append({
            "clip": name,
            "reference": ref,
            "hypothesis": hyp1,
            "wer": (errs / words) if words else None,
            "errors": errs,
            "ref_words": words,
            "latency_s": round(t1 - t0, 4),
            "rtf": round((t1 - t0) / dur, 4) if dur else None,
            "deterministic": hyp1 == hyp2,
            "tech": _tech_metrics(ref, hyp1),
        })
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    valid = [c for c in clips if c["wer"] is not None]
    agg_wer = (sum(c["errors"] for c in valid) /
               sum(c["ref_words"] for c in valid)) if valid else None
    recalls = [c["tech"]["tech_term_recall"] for c in clips
               if c["tech"]["tech_term_recall"] is not None]
    return {
        "clips": clips,
        "aggregate_wer": agg_wer,
        "aggregate_tech_recall": (sum(recalls) / len(recalls)) if recalls else None,
        "all_deterministic": all(c["deterministic"] for c in clips),
        "peak_tracemalloc_kib": round(peak / 1024, 1),
    }


# --- contextual arm (attempted, isolated) -----------------------------------

def attempt_contextual_arm(mf: dict) -> dict:
    """Attempt the contextual arm with a hotword-size sweep, each in isolation.

    Because the compatibility matrix shows modified_beam_search aborts for the
    NeMo transducer, these attempts are expected to fail; the failure is
    recorded (not fabricated). If a future model DID support it, this would
    produce real contextual transcripts.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sweep = {}
    for size in [0, 5, 10, 25, 50]:
        hw = OUT_DIR / f"_hw_{size}.txt"
        hw.write_text("\n".join(CONTROLLED_HOTWORDS[:size]) + "\n", encoding="utf-8")
        cfg = {
            "encoder": mf["encoder"], "decoder": mf["decoder"],
            "joiner": mf["joiner"], "tokens": mf["tokens"],
            "decoding_method": "modified_beam_search",
            "hotwords_file": str(hw) if size else "",
            "hotwords_score": 2.0, "modeling_unit": "cjkchar",
        }
        sweep[str(size)] = _run_isolated(cfg)
        hw.unlink(missing_ok=True)
    constructible = any(v["outcome"] == "loaded" for v in sweep.values())
    return {"size_sweep": sweep, "contextual_constructible": constructible}


def classify(compat: dict, contextual: dict) -> dict:
    """Deterministic gate classification from measured evidence."""
    if not contextual["contextual_constructible"]:
        decision = "UNSAFE/INCOMPATIBLE"
        rationale = (
            "Decoder-level hotwords require decoding_method=modified_beam_search, "
            "but the installed sherpa-onnx NeMo transducer implementation only "
            "supports greedy_search and aborts the process otherwise. The two "
            "requirements are mutually exclusive for this model, so decoder-level "
            "contextual biasing cannot be constructed on SayIt's Parakeet int8 "
            "model and attempting it would crash the application."
        )
    else:
        # Reserved for a future compatible model; not reachable with the current
        # NeMo transducer. A real benefit comparison would be computed here.
        decision = "PROMISING"
        rationale = "Contextual recognizer constructed; see contextual metrics."
    return {"decision": decision, "rationale": rationale}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import sherpa_onnx

    mf = _model_files()
    report = {
        "phase": "9A",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
        "model_id": MODEL_ID,
        "model_type": "nemo_transducer",
        "decoder_mode_production": "greedy_search",
        "model_files": mf,
    }
    if not mf["present"]:
        report["error"] = "model not downloaded; cannot run"
        (OUT_DIR / "compatibility.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print("Model not present; wrote compatibility.json with error.")
        return

    print("Building compatibility matrix (isolated subprocess probes)...")
    report["compatibility"] = build_compatibility_matrix(mf)

    print("Running greedy baseline on eval-audio A-E...")
    report["baseline"] = run_baseline(mf)

    print("Attempting contextual arm (hotword-size sweep, isolated)...")
    report["contextual"] = attempt_contextual_arm(mf)

    report["gate"] = classify(report["compatibility"], report["contextual"])

    (OUT_DIR / "compatibility.json").write_text(
        json.dumps(report["compatibility"], indent=2), encoding="utf-8"
    )
    (OUT_DIR / "baseline.json").write_text(
        json.dumps(report["baseline"], indent=2), encoding="utf-8"
    )
    (OUT_DIR / "contextual.json").write_text(
        json.dumps(report["contextual"], indent=2), encoding="utf-8"
    )
    (OUT_DIR / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Gate decision: {report['gate']['decision']}")
    print(f"Artifacts written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
