"""Phase 9F benchmark — contextual candidate ranking + false-positive control.

Arms (same greedy ASR / model / decoder, raw-ASR metrics, no 6G/6I/6J):
  A: raw greedy transcript
  B: raw + 9B manual curated pack
  C: raw + 9C automatic retrieval (no ranker; the 9C adapter)
  D: raw + 9C retrieve-once + 9F ranking + 9B correction (the ranked adapter)

Plus: ablation A-F, Recall@1/3/5/10, threshold + margin sweeps, retrieve-once
latency vs the 9C per-span adapter, hard-negative per-pair, determinism, RSS.
Emits artifacts/phase9f/*.json.
"""

from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))

import metrics as M  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.candidate_ranker import CandidateRanker, Decision, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import CorrectorConfig, PostASRContextCorrector  # noqa: E402
from sayit.core.asr.post_context_pack import default_pack as manual_pack  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.adapter import RetrievalCorrectionAdapter  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.models import normalize_text  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"
OUT = ROOT / "artifacts" / "phase9f"


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
        out.append({"id": e["id"], "ref": e["reference"], "hyp": s.result.text.strip(),
                    "targets": e.get("target_terms", []), "negs": e.get("negative_terms", []),
                    "phrases": e.get("phrase_terms", []), "context": context_for(e),
                    "pair_id": e.get("pair_id"), "pair_role": e.get("pair_role")})
    return out


def score(clips, transform):
    recs = []
    per = {}
    for c in clips:
        hyp = transform(c)
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        ph_n, ph_d, _ = M.phrase_recall(hyp, c["phrases"] or c["targets"])
        fs_n, _ = M.false_technical_substitutions(hyp, c["negs"])
        r = {"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
             "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": ph_n,
             "phrase_total": ph_d, "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
             "ordinary_preserved": (fs_n == 0) if c["negs"] else None, "hyp": hyp}
        per[c["id"]] = r
        recs.append(r)
    return M.aggregate(recs), per


def spans_of(text, max_w=3):
    w = text.split()
    return [" ".join(w[i:i + L]) for i in range(len(w)) for L in range(1, min(max_w, len(w) - i) + 1)]


def recall_at_k(clips, retriever, ranker):
    ks = [1, 3, 5, 10]
    hits = {k: 0 for k in ks}
    total = 0
    for c in clips:
        for target in c["targets"]:
            total += 1
            tnorm = normalize_text(target)
            best = None
            for span in spans_of(c["hyp"]):
                cands = retriever.retrieve(span, c["context"], top_k=10)
                dec = ranker.rank(span, cands, c["context"])
                for rank_i, rc in enumerate(dec.ranked, 1):
                    if normalize_text(rc.canonical) == tnorm:
                        best = rank_i if best is None else min(best, rank_i)
                        break
            for k in ks:
                if best is not None and best <= k:
                    hits[k] += 1
    return {f"recall@{k}": (hits[k] / total if total else None) for k in ks} | {"target_count": total}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    index = KnowledgeIndex.load(IDX)
    retriever = CandidateRetriever(index)
    ranker = CandidateRanker(RankerConfig())
    c_adapter = RetrievalCorrectionAdapter(retriever, CorrectorConfig(), top_k=10)
    d_adapter = RankedRetrievalAdapter(retriever, ranker, CorrectorConfig(), top_k=10)
    manual = PostASRContextCorrector(manual_pack(), CorrectorConfig())

    def arm(label, transform):
        t0 = time.perf_counter()
        agg, per = score(clips, transform)
        lat_ms = (time.perf_counter() - t0) / len(clips) * 1000.0
        return {"aggregate": agg, "per_clip": per, "median_latency_ms_est": round(lat_ms, 3)}

    arms = {
        "A_raw": arm("A", lambda c: c["hyp"]),
        "B_9B_manual": arm("B", lambda c: manual.correct(c["hyp"], c["context"]).text),
        "C_9C_retrieval": arm("C", lambda c: c_adapter.correct(c["hyp"], c["context"]).text),
        "D_9C_9F_9B": arm("D", lambda c: d_adapter.correct(c["hyp"], c["context"]).text),
    }
    (OUT / "benchmark.json").write_text(json.dumps(
        {k: {"aggregate": v["aggregate"], "latency_ms_est": v["median_latency_ms_est"]}
         for k, v in arms.items()}, indent=2), encoding="utf-8")

    # Recall@K (post-ranking order).
    (OUT / "recall_at_k.json").write_text(
        json.dumps(recall_at_k(clips, retriever, ranker), indent=2), encoding="utf-8")

    # Ablation A-F.
    def run_ranked(cfg):
        ad = RankedRetrievalAdapter(retriever, CandidateRanker(cfg), CorrectorConfig(), top_k=10)
        agg, _ = score(clips, lambda c: ad.correct(c["hyp"], c["context"]).text)
        return {"technical_term_recall": agg["technical_term_recall"],
                "exact_entity_accuracy": agg["exact_entity_accuracy"],
                "false_substitution_total": agg["false_substitution_total"],
                "ordinary_preservation": agg["ordinary_preservation"], "wer": agg["wer"]}
    ablation = {
        "A_retrieval_only": arms["C_9C_retrieval"]["aggregate"],
        "B_rank_no_context_source": run_ranked(RankerConfig(use_context=False, use_source_confidence=False, use_ambiguity=False, use_ordinary_penalty=False)),
        "C_rank_context": run_ranked(RankerConfig(use_source_confidence=False, use_ambiguity=False, use_ordinary_penalty=False)),
        "D_rank_context_source": run_ranked(RankerConfig(use_ambiguity=False, use_ordinary_penalty=False)),
        "E_full_penalties": run_ranked(RankerConfig(use_abstention=True)),
        "F_full_abstention": run_ranked(RankerConfig()),
    }
    # normalize arm C aggregate to the ablation metric shape
    c = ablation["A_retrieval_only"]
    ablation["A_retrieval_only"] = {"technical_term_recall": c["technical_term_recall"],
        "exact_entity_accuracy": c["exact_entity_accuracy"],
        "false_substitution_total": c["false_substitution_total"],
        "ordinary_preservation": c["ordinary_preservation"], "wer": c["wer"]}
    (OUT / "ablation.json").write_text(json.dumps(ablation, indent=2), encoding="utf-8")

    # Threshold + margin sweeps (on arm D).
    tsweep = {}
    for th in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        tsweep[str(th)] = run_ranked(RankerConfig(accept_threshold=th))
    (OUT / "threshold_sweep.json").write_text(json.dumps(tsweep, indent=2), encoding="utf-8")
    msweep = {}
    for mg in [0.00, 0.04, 0.08, 0.12, 0.16, 0.20]:
        msweep[str(mg)] = run_ranked(RankerConfig(margin=mg))
    (OUT / "margin_sweep.json").write_text(json.dumps(msweep, indent=2), encoding="utf-8")

    # Hard negatives per pair.
    pairs = {}
    for c in clips:
        if c["pair_id"]:
            pairs.setdefault(c["pair_id"], {})[c["pair_role"]] = c
    hn = {}
    for pid, roles in pairs.items():
        if "ordinary" in roles and "technical" in roles:
            o, t = roles["ordinary"], roles["technical"]
            hn[pid] = {
                "ordinary_raw": o["hyp"], "ordinary_corrected": d_adapter.correct(o["hyp"], o["context"]).text,
                "ordinary_negs": o["negs"],
                "technical_raw": t["hyp"], "technical_corrected": d_adapter.correct(t["hyp"], t["context"]).text,
                "technical_targets": t["targets"],
            }
    (OUT / "hard_negative_results.json").write_text(
        json.dumps({"pairs": list(hn), "analysis": hn}, indent=2), encoding="utf-8")

    # Retrieve-once latency vs 9C per-span adapter + determinism + RSS.
    sample = [(c["hyp"], c["context"]) for c in clips]
    for _ in range(10):
        for h, ctx in sample:
            d_adapter.correct(h, ctx)
    def med_latency(ad, N=30):
        ts = []
        for _ in range(N):
            for h, ctx in sample:
                t0 = time.perf_counter(); ad.correct(h, ctx); ts.append((time.perf_counter() - t0) * 1000)
        ts.sort()
        return round(ts[len(ts) // 2], 3), round(ts[int(len(ts) * 0.95)], 3)
    d_med, d_p95 = med_latency(d_adapter)
    c_med, c_p95 = med_latency(c_adapter)
    runs = [{c["id"]: d_adapter.correct(c["hyp"], c["context"]).text for c in clips} for _ in range(3)]
    deterministic = runs[0] == runs[1] == runs[2]
    try:
        import psutil
        rss = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        rss = None
    perf = {
        "arm_D_ranked_adapter_median_ms": d_med, "arm_D_ranked_adapter_p95_ms": d_p95,
        "arm_C_9C_adapter_median_ms": c_med, "arm_C_9C_adapter_p95_ms": c_p95,
        "retrieve_once_vs_perspan_note": "arm D retrieves once per span then ranks; arm C (9C) re-retrieves inside the corrector scan",
        "process_rss_mib": rss, "deterministic_x3": deterministic,
    }
    (OUT / "performance.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    (OUT / "wordfreq_experiment.json").write_text(json.dumps(
        {"run": False, "reason": "wordfreq not installed; optional per 9F-J; not auto-added. "
         "Documented as future isolated experiment."}, indent=2), encoding="utf-8")

    for k in ("A_raw", "B_9B_manual", "C_9C_retrieval", "D_9C_9F_9B"):
        a = arms[k]["aggregate"]
        print(k, "recall=%.3f exact=%.3f phrase=%.3f fsub=%d ordinary=%.3f wer=%.3f lat=%.1fms" % (
            a["technical_term_recall"], a["exact_entity_accuracy"], a["phrase_recall"],
            a["false_substitution_total"], a["ordinary_preservation"], a["wer"],
            arms[k]["median_latency_ms_est"]))
    print("perf:", perf)


if __name__ == "__main__":
    main()
