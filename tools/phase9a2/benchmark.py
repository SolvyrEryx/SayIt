"""Phase 9A.2 — recognition benchmark harness (ISOLATED).

Runs in the isolated upstream venv (tools/phase9a1/.venv-upstream, sherpa_onnx
1.13.8). Self-contained except for importing the pure metric/validator modules
by path (they depend only on stdlib). The production sayit package is never
imported.

Three decoder arms on IDENTICAL audio for every scored clip:
    A greedy   : greedy_search                           (production decoder)
    B beam     : modified_beam_search + modeling_unit=bpe (decoder effect)
    C hotword  : modified_beam_search + bpe + hotwords    (decoder + hotword)

Note on versions: the production control is greedy_search on sherpa_onnx
1.12.21. Phase 9A.1 already established greedy output is byte-identical in intent
between 1.12.21 and 1.13.8 on this corpus; to guarantee an apples-to-apples
SAME-interpreter/SAME-preprocessing comparison here, all three arms run in the
1.13.8 venv and arm A is labeled "greedy (1.13.8, control-equivalent)". The
production 1.12.21 greedy numbers from artifacts/phase9/9A1 remain the true
production control and are cross-referenced in the report.

Only RAW ASR is scored (no 6G/6I/6J/8H).

Usage (MUST use the isolated interpreter):
    .venv-upstream/python benchmark.py <model_dir> <bpe_vocab> <eval_dir> <corpus_dir> <labels_json> <out_dir>
"""

from __future__ import annotations

import json
import os
import sys
import time
import tracemalloc
import wave
from datetime import datetime, timezone

import numpy as np
import sherpa_onnx

# Import pure metric/validator modules by path (stdlib-only deps).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M  # noqa: E402
import corpus_validator as CV  # noqa: E402

CONTROLLED_HOTWORDS = [
    "PostgreSQL", "SQLAlchemy", "FastAPI", "Pydantic", "OpenAI",
    "Next.js", "React", "TensorFlow", "ONNX", "kubectl", "Kubernetes",
    "Python", "Rust", "GitHub", "Docker", "NumPy", "Pandas", "Redis",
    "Django", "Flask", "PyTorch", "WebAuthn", "OAuth2", "JWT", "TLS",
]


def read_wav(path):
    w = wave.open(path, "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr, n / sr


def make_rec(mdir, bpe_vocab, method, hotwords_file="", score=2.0):
    kw = dict(
        encoder=os.path.join(mdir, "encoder.int8.onnx"),
        decoder=os.path.join(mdir, "decoder.int8.onnx"),
        joiner=os.path.join(mdir, "joiner.int8.onnx"),
        tokens=os.path.join(mdir, "tokens.txt"),
        num_threads=4, provider="cpu",
        decoding_method=method, model_type="nemo_transducer",
    )
    if method == "modified_beam_search":
        kw["modeling_unit"] = "bpe"
        kw["bpe_vocab"] = bpe_vocab
        if hotwords_file:
            kw["hotwords_file"] = hotwords_file
            kw["hotwords_score"] = score
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kw)


def decode(rec, data, sr):
    s = rec.create_stream()
    s.accept_waveform(sr, data)
    rec.decode_stream(s)
    return s.result.text.strip()


def score_clip(entry, hyp):
    ref = entry["reference"]
    targets = entry.get("target_terms", [])
    negs = entry.get("negative_terms", [])
    phrases = entry.get("phrase_terms", [])
    errs, words = M.wer(ref, hyp)
    tr_n, tr_d, tr_list = M.technical_term_recall(hyp, targets)
    ex_n, ex_d, ex_list = M.exact_entity_accuracy(hyp, targets)
    ph_n, ph_d, ph_list = M.phrase_recall(hyp, phrases or targets)
    fs_n, fs_list = M.false_technical_substitutions(hyp, negs)
    return {
        "hypothesis": hyp,
        "errors": errs, "ref_words": words,
        "wer": (errs / words) if words else None,
        "tech_recalled": tr_n, "tech_total": tr_d, "tech_recalled_list": tr_list,
        "exact_count": ex_n, "exact_total": ex_d, "exact_list": ex_list,
        "phrase_recalled": ph_n, "phrase_total": ph_d, "phrase_list": ph_list,
        "false_sub_count": fs_n, "false_sub_list": fs_list,
        "has_negatives": bool(negs),
        "ordinary_preserved": (fs_n == 0) if negs else None,
    }


def run_arm(rec, clips, repeats=3):
    per_clip = {}
    records = []
    for entry, data, sr, dur in clips:
        hyps = [decode(rec, data, sr) for _ in range(repeats)]
        t0 = time.perf_counter()
        _ = decode(rec, data, sr)
        lat = time.perf_counter() - t0
        rec_metrics = score_clip(entry, hyps[0])
        rec_metrics["id"] = entry["id"]
        rec_metrics["category"] = entry["category"]
        rec_metrics["latency_s"] = round(lat, 4)
        rec_metrics["rtf"] = round(lat / dur, 4) if dur else None
        rec_metrics["deterministic"] = len(set(hyps)) == 1
        per_clip[entry["id"]] = rec_metrics
        records.append(rec_metrics)
    summary = M.aggregate(records)
    summary["all_deterministic"] = all(r["deterministic"] for r in records)
    summary["median_latency_s"] = round(
        sorted(r["latency_s"] for r in records)[len(records) // 2], 4
    ) if records else None
    return {"per_clip": per_clip, "summary": summary}


def main():
    mdir, bpe_vocab, eval_dir, corpus_dir, labels_json, out_dir = sys.argv[1:7]
    os.makedirs(out_dir, exist_ok=True)
    entries = json.loads(open(labels_json, encoding="utf-8").read())

    validation = CV.validate_corpus(entries)

    # Resolve audio: prefer corpus_dir/<wav>, else eval_dir/<wav> (for A-E).
    def find_wav(e):
        wav = e.get("wav", e["id"] + ".wav")
        for base in (corpus_dir, eval_dir):
            p = os.path.join(base, wav)
            if os.path.exists(p):
                return p
        return None

    scored = []
    skipped = []
    for e in CV.scored_entries(entries):
        p = find_wav(e)
        if p is None:
            skipped.append({"id": e["id"], "reason": "audio_not_found"})
            continue
        data, sr, dur = read_wav(p)
        scored.append((e, data, sr, dur))
    for e in entries:
        if e.get("needs_recording", False):
            skipped.append({"id": e["id"], "reason": "needs_recording"})

    report = {
        "phase": "9A.2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
        "model_id": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
        "corpus_validation": validation,
        "scored_clip_ids": [e["id"] for e, *_ in scored],
        "skipped": skipped,
        "controlled_hotwords": CONTROLLED_HOTWORDS,
    }

    if not scored:
        report["error"] = "no scorable audio present"
        open(os.path.join(out_dir, "benchmark_raw.json"), "w", encoding="utf-8").write(
            json.dumps(report, indent=2))
        print("No scorable audio. Wrote benchmark_raw.json with validation only.")
        return

    hw_dir = os.path.join(out_dir, "temp_hw")
    os.makedirs(hw_dir, exist_ok=True)
    hw_all = os.path.join(hw_dir, "hw_all.txt")
    open(hw_all, "w", encoding="utf-8").write("\n".join(CONTROLLED_HOTWORDS) + "\n")

    load = {}
    t = time.perf_counter(); rec_a = make_rec(mdir, bpe_vocab, "greedy_search"); load["greedy"] = round(time.perf_counter() - t, 4)
    t = time.perf_counter(); rec_b = make_rec(mdir, bpe_vocab, "modified_beam_search"); load["beam"] = round(time.perf_counter() - t, 4)
    t = time.perf_counter(); rec_c = make_rec(mdir, bpe_vocab, "modified_beam_search", hw_all, 2.0); load["hotword"] = round(time.perf_counter() - t, 4)

    tracemalloc.start()
    report["arm_A_greedy"] = run_arm(rec_a, scored)
    report["arm_B_beam"] = run_arm(rec_b, scored)
    report["arm_C_hotword"] = run_arm(rec_c, scored)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    report["performance"] = {
        "load_time_s": load,
        "peak_tracemalloc_kib": round(peak / 1024, 1),
        "memory_metric": "tracemalloc peak (python allocations only, NOT process RSS)",
    }

    open(os.path.join(out_dir, "benchmark_raw.json"), "w", encoding="utf-8").write(
        json.dumps(report, indent=2))

    # Hard-negative pair analysis (only pairs with BOTH halves scored).
    pairs = {}
    for e, *_ in scored:
        pid = e.get("pair_id")
        if pid:
            pairs.setdefault(pid, {})[e.get("pair_role")] = e["id"]
    hn = {}
    for pid, roles in pairs.items():
        if "ordinary" in roles and "technical" in roles:
            o, tch = roles["ordinary"], roles["technical"]
            hn[pid] = {
                "ordinary_id": o, "technical_id": tch,
                "ordinary": {
                    arm: report[f"arm_{a}"]["per_clip"][o]
                    for arm, a in [("greedy", "A_greedy"), ("beam", "B_beam"), ("hotword", "C_hotword")]
                },
                "technical": {
                    arm: report[f"arm_{a}"]["per_clip"][tch]
                    for arm, a in [("greedy", "A_greedy"), ("beam", "B_beam"), ("hotword", "C_hotword")]
                },
            }
    open(os.path.join(out_dir, "hard_negatives.json"), "w", encoding="utf-8").write(
        json.dumps({"pairs_with_both_halves": list(hn.keys()), "analysis": hn}, indent=2))

    # Score + count sweeps on the technical clips present.
    tech_clips = [(e, d, s, du) for (e, d, s, du) in scored if e.get("target_terms")]
    sweeps = {"score_sweep": {}, "count_sweep": {}, "note": "on scored technical clips"}
    if tech_clips:
        for sc in [0.5, 1.0, 1.5, 2.0, 2.5]:
            r = make_rec(mdir, bpe_vocab, "modified_beam_search", hw_all, sc)
            sweeps["score_sweep"][str(sc)] = {
                e["id"]: decode(r, d, s) for (e, d, s, du) in tech_clips
            }
        for cnt in [0, 1, 5, 10, 25]:
            if cnt == 0:
                sweeps["count_sweep"]["0"] = {
                    e["id"]: decode(rec_b, d, s) for (e, d, s, du) in tech_clips
                }
                continue
            hwf = os.path.join(hw_dir, f"hw_{cnt}.txt")
            open(hwf, "w", encoding="utf-8").write("\n".join(CONTROLLED_HOTWORDS[:cnt]) + "\n")
            r = make_rec(mdir, bpe_vocab, "modified_beam_search", hwf, 2.0)
            sweeps["count_sweep"][str(cnt)] = {
                e["id"]: decode(r, d, s) for (e, d, s, du) in tech_clips
            }
    open(os.path.join(out_dir, "sweeps.json"), "w", encoding="utf-8").write(
        json.dumps(sweeps, indent=2))

    open(os.path.join(out_dir, "performance.json"), "w", encoding="utf-8").write(
        json.dumps(report["performance"], indent=2))

    print("WROTE benchmark_raw.json, hard_negatives.json, sweeps.json, performance.json")
    for arm in ("arm_A_greedy", "arm_B_beam", "arm_C_hotword"):
        s = report[arm]["summary"]
        print(arm, "WER=", s["wer"], "techRecall=", s["technical_term_recall"],
              "exact=", s["exact_entity_accuracy"], "falseSub=", s["false_substitution_total"])


if __name__ == "__main__":
    main()
