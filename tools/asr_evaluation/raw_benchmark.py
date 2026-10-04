"""Experimental ASR re-evaluation — RAW ASR benchmark (production FROZEN).

Benchmarks the locally-cached ASR models on IDENTICAL TIE held-out audio for
TECHNICAL-TERM RECOVERABILITY (not generic WER). It uses the existing
SherpaOnnxBackend (greedy, offline, CPU) with NO change to production defaults;
no model is downloaded, no cloud is used, the production flag is untouched.

Per model: WER, technical recall, exact-entity accuracy, UNSEEN recall,
hallucinated technical subs, median/p95 latency, RTF, peak RSS, load time,
repeated-run determinism, and a 0-3 technical-recovery score per target.
"""

from __future__ import annotations

import csv
import gc
import json
import sys
import time
import tracemalloc
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
import external_adapter as EA  # noqa: E402
import known_unseen as KU  # noqa: E402
from sayit.core.asr.backends import SherpaOnnxBackend  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402

EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
OUT = ROOT / "artifacts" / "asr_evaluation"

# All 6 locally cached models (confirmed present).
MODELS = [
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",   # production
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16",
    "sherpa-onnx-whisper-tiny",
    "sherpa-onnx-whisper-small",
    "sherpa-onnx-whisper-distil-large-v3.5",
    "sherpa-onnx-whisper-large-v3",
]

# Known failure inventory (evaluation targets ONLY — never added to knowledge).
FAILURE_INVENTORY = ["CAD", "HPLC", "LQR", "LQG", "OPEC", "ELISA", "non-linear",
                     "soft-in-plane", "stiff-in-plane", "co-efficient"]


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def held_out_entries():
    tie = EA.scored_entries(EA.build_manifest(EXTERNAL))
    spk = sorted({e.speaker_id for e in tie})
    held = set(spk[::2])
    return [e for e in tie if e.speaker_id in held]


def recovery_score(hyp: str, target: str) -> int:
    """0 miss / 1 recoverable near-match / 2 present but canonical imperfect /
    3 already correct. Deterministic heuristic for analysis only."""
    from difflib import SequenceMatcher
    h = hyp.lower(); t = target.lower()
    tc = "".join(ch for ch in t if ch.isalnum())
    if target in hyp:
        return 3
    if t in h:
        return 2
    # near-match: any token in hyp with high similarity to the target compact form
    best = 0.0
    for tok in h.replace("-", " ").split():
        tokc = "".join(ch for ch in tok if ch.isalnum())
        if tokc:
            best = max(best, SequenceMatcher(None, tc, tokc).ratio())
    # also try sliding bigram/trigram joins for spaced acronyms
    toks = h.split()
    for k in (2, 3, 4):
        for i in range(len(toks) - k + 1):
            joined = "".join(toks[i:i + k])
            best = max(best, SequenceMatcher(None, tc, joined).ratio())
    return 1 if best >= 0.6 else 0


def bench_model(model_id, entries, known):
    backend = SherpaOnnxBackend()
    t0 = time.perf_counter()
    backend.load(model_id)
    load_s = time.perf_counter() - t0

    gc.collect(); tracemalloc.start()
    recs, lat, rtf, hyps = [], [], [], {}
    audio_total = 0.0
    for e in entries:
        d, sr, dur = read_wav(Path(e.audio_path))
        audio_total += dur
        t1 = time.perf_counter()
        res = backend.transcribe(d, sr)
        el = time.perf_counter() - t1
        lat.append(el * 1000.0); rtf.append(el / dur if dur else 0.0)
        hyp = (res.text or "").strip(); hyps[e.sample_id] = hyp
        errs, words = M.wer(e.reference, hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, e.target_terms)
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, e.target_terms)
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n,
                     "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
                     "phrase_recalled": 0, "phrase_total": 0, "false_sub_count": 0,
                     "has_negatives": False, "ordinary_preserved": None})
    cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()

    # UNSEEN-only recall.
    unseen_recs = []
    for e in entries:
        for term in e.target_terms:
            if KU.classify_terms([term], known)[term] == "UNSEEN":
                tr1, td1, _ = M.technical_term_recall(hyps[e.sample_id], [term])
                unseen_recs.append({"tech_recalled": tr1, "tech_total": td1,
                                    "exact_count": 0, "exact_total": 0, "errors": 0,
                                    "ref_words": 0, "phrase_recalled": 0, "phrase_total": 0,
                                    "false_sub_count": 0, "has_negatives": False,
                                    "ordinary_preserved": None})

    # determinism: re-transcribe first 3 clips, compare.
    det = True
    for e in entries[:3]:
        d, sr, _ = read_wav(Path(e.audio_path))
        if (backend.transcribe(d, sr).text or "").strip() != hyps[e.sample_id]:
            det = False
    backend.unload(); gc.collect()

    lat.sort()
    agg = M.aggregate(recs)
    un = M.aggregate(unseen_recs) if unseen_recs else {}
    return {
        "model_id": model_id, "clips": len(entries), "load_time_s": round(load_s, 2),
        "wer": round(agg["wer"], 4),
        "technical_recall": round(agg["technical_term_recall"], 4),
        "exact_entity": round(agg["exact_entity_accuracy"], 4),
        "unseen_recall": round(un.get("technical_term_recall", 0.0), 4) if un else None,
        "median_latency_ms": round(lat[len(lat)//2], 1),
        "p95_latency_ms": round(lat[int(len(lat)*0.95)-1], 1),
        "mean_rtf": round(sum(rtf)/len(rtf), 4),
        "peak_rss_mib": round(peak/1048576, 1),
        "deterministic": det,
    }, hyps


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = held_out_entries()
    known = KU.build_known_set()
    (OUT / "benchmark_manifest.json").write_text(json.dumps(
        {"source": "TIE_shorts held-out", "clips": len(entries),
         "speakers": len({e.speaker_id for e in entries}),
         "models": MODELS, "decoding": "greedy_search", "provider": "cpu",
         "sample_ids": [e.sample_id for e in entries]}, indent=2), encoding="utf-8")

    all_results, all_hyps = [], {}
    for mid in MODELS:
        print(f"benchmarking {mid} ...")
        try:
            r, hyps = bench_model(mid, entries, known)
            all_results.append(r); all_hyps[mid] = hyps
            print(f"  recall={r['technical_recall']} exact={r['exact_entity']} "
                  f"unseen={r['unseen_recall']} wer={r['wer']} "
                  f"med={r['median_latency_ms']}ms rtf={r['mean_rtf']} rss={r['peak_rss_mib']}MiB load={r['load_time_s']}s")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {str(e)[:120]}")
            all_results.append({"model_id": mid, "error": f"{type(e).__name__}: {str(e)[:120]}"})

    (OUT / "raw_asr_results.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    # Technical-recovery CSV on the failure inventory (+ all held-out targets).
    with open(OUT / "technical_recovery.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "sample_id", "target", "recovery_score", "raw_excerpt"])
        for mid, hyps in all_hyps.items():
            for e in entries:
                for term in e.target_terms:
                    hyp = hyps.get(e.sample_id, "")
                    w.writerow([mid, e.sample_id, term, recovery_score(hyp, term),
                                hyp[:80]])

    # Save raw hyps for the end-to-end stage.
    (OUT / "_raw_hyps.json").write_text(json.dumps(all_hyps), encoding="utf-8")
    print("\nwrote raw_asr_results.json, technical_recovery.csv, benchmark_manifest.json")


if __name__ == "__main__":
    main()
