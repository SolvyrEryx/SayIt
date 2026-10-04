"""Phase 9A.1 — upstream contextual-biasing benchmark (ISOLATED).

Runs ENTIRELY inside the isolated upstream venv (tools/phase9a1/.venv-upstream,
sherpa-onnx 1.13.8). It is self-contained: it imports only sherpa_onnx + numpy
+ stdlib, so it must NOT be run with the production interpreter. The production
SayIt environment is never touched.

It uses the EXACT SayIt Parakeet TDT v2 int8 model and the shared Phase 6F
eval-audio corpus, and compares three decoder configurations on identical audio:

    greedy  : greedy_search                       (the production decoder)
    beam    : modified_beam_search + modeling_unit=bpe (decoder effect only)
    hotword : modified_beam_search + bpe + hotwords  (decoder + hotword effect)

Separating `beam` from `hotword` isolates the DECODER effect from the HOTWORD
effect, as required.

Outputs machine-readable JSON into artifacts/phase9/9A1/. Transcripts for the
controlled corpus are written only to the artifacts (controlled local store).

Usage (MUST use the isolated interpreter):
    tools/phase9a1/.venv-upstream/Scripts/python.exe \
        tools/phase9a1/benchmark_upstream.py <model_dir> <bpe_vocab> <eval_dir> <out_dir>
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import tracemalloc
import wave
from datetime import datetime, timezone

import numpy as np
import sherpa_onnx

# Controlled hotword vocabulary (Phase 9A.1 secondary targets + the motivating
# PostgreSQL case). Small and deliberate; no external datasets.
CONTROLLED = [
    "PostgreSQL", "Python", "GitHub", "FastAPI", "SQLAlchemy",
    "Kubernetes", "TensorFlow", "PyTorch", "OpenAI", "WebAuthn", "OAuth2",
]

# Expected technical terms per clip (lowercased, alnum) for RAW recall.
CLIP_TARGETS = {
    "D": ["github", "python", "postgresql"],
    "E": ["tls", "firewall"],  # 'cicd' is spoken-form, not a raw ASR target
}


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def wer(ref, hyp):
    r, h = _norm(ref), _norm(hyp)
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            c = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + c)
    return dp[len(r)][len(h)], len(r)


def read_wav(path):
    w = wave.open(path, "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr, n / sr


def make_recognizer(mdir, bpe_vocab, method, hotwords_file="", score=2.0):
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


def tech_recall(clip, hyp):
    targets = CLIP_TARGETS.get(clip, [])
    if not targets:
        return None, [], []
    hset = set(_norm(hyp))
    recalled = [t for t in targets if t in hset]
    return len(recalled) / len(targets), recalled, targets


def false_subs(ref, hyp):
    """Controlled hotword tokens appearing in hyp but not ref (wrongly forced)."""
    hw = set(_norm(" ".join(CONTROLLED)))
    return sorted((hw & set(_norm(hyp))) - set(_norm(ref)))


def run_corpus(rec, eval_dir, clips=("A", "B", "C", "D", "E"), repeats=3):
    out = []
    for name in clips:
        wav = os.path.join(eval_dir, f"{name}.wav")
        ref_file = os.path.join(eval_dir, f"{name}.txt")
        if not (os.path.exists(wav) and os.path.exists(ref_file)):
            continue
        data, sr, dur = read_wav(wav)
        ref = open(ref_file, encoding="utf-8").read().strip()
        hyps, lat = [], []
        for _ in range(repeats):
            t0 = time.perf_counter()
            hyps.append(decode(rec, data, sr))
            lat.append(time.perf_counter() - t0)
        errs, words = wer(ref, hyps[0])
        rc, recalled, targets = tech_recall(name, hyps[0])
        out.append({
            "clip": name, "reference": ref, "hypothesis": hyps[0],
            "wer": (errs / words) if words else None, "errors": errs,
            "ref_words": words,
            "tech_targets": targets, "tech_recalled": recalled,
            "tech_recall": rc,
            "false_substitution_tokens": false_subs(ref, hyps[0]),
            "latency_s": round(min(lat), 4),
            "rtf": round(min(lat) / dur, 4) if dur else None,
            "deterministic": len(set(hyps)) == 1,
        })
    valid = [c for c in out if c["wer"] is not None]
    agg = (sum(c["errors"] for c in valid) /
           sum(c["ref_words"] for c in valid)) if valid else None
    rcs = [c["tech_recall"] for c in out if c["tech_recall"] is not None]
    return {
        "clips": out,
        "aggregate_wer": agg,
        "aggregate_tech_recall": (sum(rcs) / len(rcs)) if rcs else None,
        "all_deterministic": all(c["deterministic"] for c in out),
    }


def main():
    mdir, bpe_vocab, eval_dir, out_dir = sys.argv[1:5]
    os.makedirs(out_dir, exist_ok=True)
    hw_dir = os.path.join(out_dir, "temp_bpe_vocab")
    os.makedirs(hw_dir, exist_ok=True)

    report = {
        "phase": "9A.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
        "model_id": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
        "model_type": "nemo_transducer",
    }

    # Load timings per config.
    load = {}
    t = time.perf_counter(); rec_g = make_recognizer(mdir, bpe_vocab, "greedy_search"); load["greedy"] = round(time.perf_counter() - t, 4)
    t = time.perf_counter(); rec_b = make_recognizer(mdir, bpe_vocab, "modified_beam_search"); load["beam"] = round(time.perf_counter() - t, 4)
    hw_all = os.path.join(hw_dir, "_hw_all.txt")
    open(hw_all, "w", encoding="utf-8").write("\n".join(CONTROLLED) + "\n")
    t = time.perf_counter(); rec_h = make_recognizer(mdir, bpe_vocab, "modified_beam_search", hw_all, 2.0); load["hotword"] = round(time.perf_counter() - t, 4)
    report["load_time_s"] = load

    tracemalloc.start()
    report["greedy"] = run_corpus(rec_g, eval_dir)
    report["beam"] = run_corpus(rec_b, eval_dir)
    report["hotword"] = run_corpus(rec_h, eval_dir)
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["peak_tracemalloc_kib"] = round(peak / 1024, 1)

    # PostgreSQL-focused: clip D with just PostgreSQL as a single hotword.
    hw_pg = os.path.join(hw_dir, "_hw_pg.txt")
    open(hw_pg, "w", encoding="utf-8").write("PostgreSQL\n")
    rec_pg = make_recognizer(mdir, bpe_vocab, "modified_beam_search", hw_pg, 2.0)
    d_wav = os.path.join(eval_dir, "D.wav")
    if os.path.exists(d_wav):
        data, sr, _ = read_wav(d_wav)
        report["postgresql_single_hotword"] = {
            "greedy": decode(rec_g, data, sr),
            "beam_no_hw": decode(rec_b, data, sr),
            "beam_hw_postgresql": decode(rec_pg, data, sr),
        }

    # Score sweep on clip D (single PostgreSQL hotword).
    if os.path.exists(d_wav):
        data, sr, _ = read_wav(d_wav)
        sweep = {}
        for sc in [0.5, 1.0, 1.5, 2.0, 2.5]:
            r = make_recognizer(mdir, bpe_vocab, "modified_beam_search", hw_pg, sc)
            sweep[str(sc)] = decode(r, data, sr)
        report["score_sweep_clipD"] = sweep

    # Count sweep on clip D (0/1/5/10 controlled terms).
    if os.path.exists(d_wav):
        data, sr, _ = read_wav(d_wav)
        csweep = {}
        for cnt in [0, 1, 5, 10]:
            if cnt == 0:
                csweep["0"] = decode(rec_b, data, sr)
                continue
            hwf = os.path.join(hw_dir, f"_hw_{cnt}.txt")
            open(hwf, "w", encoding="utf-8").write("\n".join(CONTROLLED[:cnt]) + "\n")
            r = make_recognizer(mdir, bpe_vocab, "modified_beam_search", hwf, 2.0)
            csweep[str(cnt)] = decode(r, data, sr)
        report["count_sweep_clipD"] = csweep

    open(os.path.join(out_dir, "upstream_report.json"), "w", encoding="utf-8").write(
        json.dumps(report, indent=2)
    )
    print("WROTE upstream_report.json")
    print("greedy WER=", report["greedy"]["aggregate_wer"],
          "beam WER=", report["beam"]["aggregate_wer"],
          "hotword WER=", report["hotword"]["aggregate_wer"])
    if "postgresql_single_hotword" in report:
        print("PG:", json.dumps(report["postgresql_single_hotword"]))


if __name__ == "__main__":
    main()
