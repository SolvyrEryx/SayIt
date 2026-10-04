"""Phase 9B — post-ASR contextual correction benchmark (ISOLATED, raw-ASR).

Arm A: raw greedy Parakeet transcript (production decoder, UNCHANGED).
Arm B: same raw transcript + PostASRContextCorrector.

The ASR decoder/model/dependency are identical between arms — only post-ASR
processing differs. 6G/6I/6J/8H are NOT applied (raw-ASR evaluation).

Context assignment reflects the realistic scenario: hard-negative TECHNICAL
halves + the technical clips D/E/MULTI are evaluated under 'developer' context;
hard-negative ORDINARY halves + ordinary clips A/B/C under 'email' (ordinary).
This tests whether correction recovers technical errors under technical context
WITHOUT corrupting ordinary speech under ordinary context.

Runs on the production interpreter (greedy only; no beam, no hotwords).

Usage:
    uv run python tools/phase9b/benchmark.py
"""

from __future__ import annotations

import json
import os
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

import metrics as M  # noqa: E402  (reuse 9A.2 raw-ASR metrics)
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.post_context import (  # noqa: E402
    CorrectorConfig, PostASRContextCorrector,
)
from sayit.core.asr.post_context_pack import all_candidates, default_pack  # noqa: E402
from sayit.core.asr.post_context import CandidatePack  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
OUT = ROOT / "artifacts" / "phase9" / "9B"


def read_wav(p):
    w = wave.open(str(p), "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr, n / sr


def find_wav(e):
    wav = e.get("wav", e["id"] + ".wav")
    for base in (CORPUS, EVAL):
        p = base / wav
        if p.exists():
            return p
    return None


def context_for(entry) -> str:
    """Deterministic context assignment for the benchmark."""
    role = entry.get("pair_role")
    cat = entry.get("category")
    if role == "technical" or cat in ("technical", "multiword"):
        return "developer"
    if role == "ordinary":
        return "email"      # ordinary context -> correction should NOT fire
    if cat == "mixed":
        return "developer"  # mixed sentence in a dev setting
    return "email"


def score_clip(entry, hyp):
    targets = entry.get("target_terms", [])
    negs = entry.get("negative_terms", [])
    phrases = entry.get("phrase_terms", [])
    errs, words = M.wer(entry["reference"], hyp)
    tr_n, tr_d, _ = M.technical_term_recall(hyp, targets)
    ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, targets)
    ph_n, ph_d, _ = M.phrase_recall(hyp, phrases or targets)
    fs_n, fs_list = M.false_technical_substitutions(hyp, negs)
    return {
        "errors": errs, "ref_words": words,
        "tech_recalled": tr_n, "tech_total": tr_d,
        "exact_count": ex_n, "exact_total": ex_d,
        "phrase_recalled": ph_n, "phrase_total": ph_d,
        "false_sub_count": fs_n, "false_sub_list": fs_list,
        "has_negatives": bool(negs),
        "ordinary_preserved": (fs_n == 0) if negs else None,
    }


def main():
    import sherpa_onnx

    OUT.mkdir(parents=True, exist_ok=True)
    entries = [e for e in json.loads(LABELS.read_text(encoding="utf-8"))
               if not e.get("needs_recording", False)]
    clips = []
    for e in entries:
        p = find_wav(e)
        if p is not None:
            clips.append((e, p))

    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer",
    )

    # 1) Raw greedy transcripts (Arm A) — decoder UNCHANGED.
    raw = {}
    for e, p in clips:
        data, sr, dur = read_wav(p)
        s = rec.create_stream()
        s.accept_waveform(sr, data)
        rec.decode_stream(s)
        raw[e["id"]] = {"hyp": s.result.text.strip(), "context": context_for(e)}

    def run_arm(corrector):
        recs = []
        per_clip = {}
        for e, _ in clips:
            hyp_raw = raw[e["id"]]["hyp"]
            if corrector is None:
                hyp = hyp_raw
                decisions = []
            else:
                r = corrector.correct(hyp_raw, raw[e["id"]]["context"])
                hyp = r.text
                decisions = [{"span": d.original_span, "repl": d.replacement,
                              "reason": d.reason, "score": d.best_score,
                              "margin": d.margin} for d in r.decisions if d.changed]
            m = score_clip(e, hyp)
            m["id"] = e["id"]
            m["context"] = raw[e["id"]]["context"]
            m["hyp"] = hyp
            m["decisions"] = decisions
            per_clip[e["id"]] = m
            recs.append(m)
        agg = M.aggregate(recs)
        return {"aggregate": agg, "per_clip": per_clip}

    base_cfg = CorrectorConfig()
    arm_a = run_arm(None)
    arm_b = run_arm(PostASRContextCorrector(default_pack(), base_cfg))

    (OUT / "baseline.json").write_text(json.dumps(
        {"model_id": MODEL_ID, "decoder": "greedy_search",
         "timestamp": datetime.now(timezone.utc).isoformat(),
         "arm_A_raw": arm_a}, indent=2), encoding="utf-8")
    (OUT / "correction_results.json").write_text(json.dumps(
        {"config": base_cfg.__dict__, "arm_B_corrected": arm_b,
         "arm_A_aggregate": arm_a["aggregate"]}, indent=2), encoding="utf-8")

    # 2) Hard-negative per-pair (raw vs corrected).
    pairs = {}
    for e, _ in clips:
        pid = e.get("pair_id")
        if pid:
            pairs.setdefault(pid, {})[e.get("pair_role")] = e["id"]
    hn = {}
    for pid, roles in pairs.items():
        if "ordinary" in roles and "technical" in roles:
            o, t = roles["ordinary"], roles["technical"]
            hn[pid] = {
                "ordinary": {"raw": arm_a["per_clip"][o], "corrected": arm_b["per_clip"][o]},
                "technical": {"raw": arm_a["per_clip"][t], "corrected": arm_b["per_clip"][t]},
            }
    (OUT / "hard_negative_results.json").write_text(
        json.dumps({"pairs": list(hn), "analysis": hn}, indent=2), encoding="utf-8")

    # 3) Ablations: A sim-only, B +context, C +context+margin, D +all.
    ablations = {}
    for name, cfg in [
        ("A_similarity_only", CorrectorConfig(use_context=False, use_margin=False, use_negative_protection=False)),
        ("B_plus_context", CorrectorConfig(use_context=True, use_margin=False, use_negative_protection=False)),
        ("C_plus_margin", CorrectorConfig(use_context=True, use_margin=True, use_negative_protection=False)),
        ("D_plus_negative", CorrectorConfig(use_context=True, use_margin=True, use_negative_protection=True)),
    ]:
        res = run_arm(PostASRContextCorrector(default_pack(), cfg))
        ablations[name] = res["aggregate"]
    (OUT / "ablation.json").write_text(json.dumps(ablations, indent=2), encoding="utf-8")

    # 4) Threshold sweep.
    tsweep = {}
    for th in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        res = run_arm(PostASRContextCorrector(default_pack(), CorrectorConfig(threshold=th)))
        tsweep[str(th)] = res["aggregate"]
    (OUT / "threshold_sweep.json").write_text(json.dumps(tsweep, indent=2), encoding="utf-8")

    # 5) Margin sweep.
    msweep = {}
    for mg in [0.00, 0.05, 0.10, 0.15, 0.20]:
        res = run_arm(PostASRContextCorrector(default_pack(), CorrectorConfig(margin=mg)))
        msweep[str(mg)] = res["aggregate"]
    (OUT / "margin_sweep.json").write_text(json.dumps(msweep, indent=2), encoding="utf-8")

    # 6) Candidate-count sweep.
    csweep = {}
    allc = all_candidates()
    for cnt in [5, 10, 20, 50]:
        pack = CandidatePack(allc[:cnt])
        res = run_arm(PostASRContextCorrector(pack, CorrectorConfig()))
        csweep[str(cnt)] = res["aggregate"]
    (OUT / "candidate_count_sweep.json").write_text(json.dumps(csweep, indent=2), encoding="utf-8")

    # 7) Performance + determinism (correction only; ASR excluded).
    corrector = PostASRContextCorrector(default_pack(), base_cfg)
    sample = [(raw[e["id"]]["hyp"], raw[e["id"]]["context"]) for e, _ in clips]
    for _ in range(50):
        for h, ctx in sample:
            corrector.correct(h, ctx)
    t0 = time.perf_counter()
    N = 200
    for _ in range(N):
        for h, ctx in sample:
            corrector.correct(h, ctx)
    per_call_ms = (time.perf_counter() - t0) / (N * len(sample)) * 1000.0
    tracemalloc.start()
    for h, ctx in sample:
        corrector.correct(h, ctx)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # Determinism x3.
    runs = []
    for _ in range(3):
        runs.append({e["id"]: corrector.correct(raw[e["id"]]["hyp"], raw[e["id"]]["context"]).text
                     for e, _ in clips})
    deterministic = runs[0] == runs[1] == runs[2]
    (OUT / "performance.json").write_text(json.dumps({
        "correction_per_call_ms_median_est": round(per_call_ms, 5),
        "correction_tracemalloc_peak_kib": round(peak / 1024, 1),
        "memory_metric": "tracemalloc peak (python allocations only, not RSS)",
        "deterministic_x3": deterministic,
        "note": "correction latency excludes ASR; ASR greedy is unchanged.",
    }, indent=2), encoding="utf-8")

    # Console summary.
    a, b = arm_a["aggregate"], arm_b["aggregate"]
    print("ARM A (raw):     WER=%.3f recall=%.3f exact=%.3f falseSub=%d" % (
        a["wer"], a["technical_term_recall"], a["exact_entity_accuracy"], a["false_substitution_total"]))
    print("ARM B (corrected): WER=%.3f recall=%.3f exact=%.3f falseSub=%d" % (
        b["wer"], b["technical_term_recall"], b["exact_entity_accuracy"], b["false_substitution_total"]))
    print("per-call correction: %.4f ms ; deterministic=%s" % (per_call_ms, deterministic))


if __name__ == "__main__":
    main()
