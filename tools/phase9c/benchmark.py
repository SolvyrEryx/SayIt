"""Phase 9C benchmark — local knowledge retrieval + end-to-end 9B correction.

Runs on the production interpreter (greedy ASR unchanged). Measures:
  - Recall@K: for each corpus target term, does retrieval surface it in top-K
    when queried with the mis-heard span (and with the full transcript spans)?
  - End-to-end: RAW greedy -> RETRIEVAL -> 9B correction, vs 9B with the manual
    9B pack (does automatic retrieval match manual-candidate performance?).
  - Source ablation: curated-only / linguist-only / npm+pypi-only / combined.
  - Hard-negative preservation; latency; RSS; determinism.

Emits artifacts/phase9/9C/*.json.
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
from sayit.core.asr.post_context import CorrectorConfig, PostASRContextCorrector  # noqa: E402
from sayit.core.asr.post_context_pack import default_pack as manual_pack  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.adapter import RetrievalCorrectionAdapter  # noqa: E402
from sayit.core.knowledge.index import KnowledgeIndex as KI  # noqa: E402
from sayit.core.knowledge.models import KnowledgeTerm, normalize_text  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"
INGESTED = ROOT / "artifacts" / "phase9" / "9C" / "ingested"
OUT = ROOT / "artifacts" / "phase9" / "9C"


def read_wav(p):
    w = wave.open(str(p), "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def find_wav(e):
    wav = e.get("wav", e["id"] + ".wav")
    for base in (CORPUS, EVAL):
        p = base / wav
        if p.exists():
            return p
    return None


def context_for(e):
    role = e.get("pair_role")
    cat = e.get("category")
    if role == "technical" or cat in ("technical", "multiword"):
        return "developer"
    if role == "ordinary":
        return "email"
    if cat == "mixed":
        return "developer"
    return "email"


def greedy_transcripts():
    import sherpa_onnx

    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    entries = [e for e in json.loads(LABELS.read_text(encoding="utf-8"))
               if not e.get("needs_recording", False)]
    clips = []
    for e in entries:
        p = find_wav(e)
        if p is None:
            continue
        d, sr, _ = read_wav(p)
        s = rec.create_stream()
        s.accept_waveform(sr, d)
        rec.decode_stream(s)
        clips.append({"id": e["id"], "ref": e["reference"], "hyp": s.result.text.strip(),
                      "targets": e.get("target_terms", []), "negs": e.get("negative_terms", []),
                      "phrases": e.get("phrase_terms", []), "context": context_for(e),
                      "pair_id": e.get("pair_id"), "pair_role": e.get("pair_role")})
    return clips


def spans_of(text, max_w=3):
    words = text.split()
    out = []
    for i in range(len(words)):
        for L in range(1, min(max_w, len(words) - i) + 1):
            out.append(" ".join(words[i:i + L]))
    return out


def recall_at_k(clips, retriever):
    """For each clip with target terms, check whether each target appears in the
    retriever's top-K over ANY span of the clip's transcript."""
    ks = [1, 5, 10, 20, 50]
    hits = {k: 0 for k in ks}
    total = 0
    detail = []
    for c in clips:
        for target in c["targets"]:
            total += 1
            tnorm = normalize_text(target)
            found_rank = None
            # Best (smallest) rank at which the target appears across spans.
            for span in spans_of(c["hyp"]):
                cands = retriever.retrieve(span, c["context"], top_k=50)
                for rank, rc in enumerate(cands, 1):
                    if normalize_text(rc.term.canonical) == tnorm:
                        found_rank = rank if found_rank is None else min(found_rank, rank)
                        break
            for k in ks:
                if found_rank is not None and found_rank <= k:
                    hits[k] += 1
            detail.append({"clip": c["id"], "target": target, "rank": found_rank})
    recall = {f"recall@{k}": (hits[k] / total if total else None) for k in ks}
    recall["target_count"] = total
    return recall, detail


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
        rec = {"errors": errs, "ref_words": words, "tech_recalled": tr_n,
               "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
               "phrase_recalled": ph_n, "phrase_total": ph_d,
               "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
               "ordinary_preserved": (fs_n == 0) if c["negs"] else None, "hyp": hyp}
        per[c["id"]] = rec
        recs.append(rec)
    agg = M.aggregate(recs)
    return agg, per


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_transcripts()
    index = KnowledgeIndex.load(IDX)
    retriever = CandidateRetriever(index)
    adapter = RetrievalCorrectionAdapter(retriever, CorrectorConfig(), top_k=10)

    # 1) Recall@K.
    recall, recall_detail = recall_at_k(clips, retriever)
    (OUT / "retrieval_benchmark.json").write_text(
        json.dumps({"recall": recall, "detail": recall_detail}, indent=2), encoding="utf-8")

    # 2) End-to-end arms.
    raw_agg, _ = score(clips, lambda c: c["hyp"])
    manual = PostASRContextCorrector(manual_pack(), CorrectorConfig())
    manual_agg, _ = score(clips, lambda c: manual.correct(c["hyp"], c["context"]).text)
    retr_agg, retr_per = score(clips, lambda c: adapter.correct(c["hyp"], c["context"]).text)
    (OUT / "end_to_end_results.json").write_text(json.dumps({
        "arm_raw": raw_agg, "arm_9B_manual_pack": manual_agg,
        "arm_9C_retrieval": retr_agg,
    }, indent=2), encoding="utf-8")

    # 3) Source ablation (which knowledge source carries the value).
    def load_src(fname):
        p = INGESTED / fname
        if not p.exists():
            return []
        return [KnowledgeTerm.from_dict(d) for d in json.loads(p.read_text(encoding="utf-8"))]

    sys.path.insert(0, str(ROOT / "tools" / "knowledge"))
    import normalize as _norm  # type: ignore
    ablation = {}
    sources = {
        "linguist_only": load_src("linguist_terms.json"),
        "npm_pypi_only": load_src("npm_pypi_terms.json"),
        "curated_only": list(_norm._CURATED_TECH),
        "combined": None,  # full index
    }
    for name, terms in sources.items():
        idx = index if terms is None else KI(terms)
        ad = RetrievalCorrectionAdapter(CandidateRetriever(idx), CorrectorConfig(), top_k=10)
        agg, _ = score(clips, lambda c, a=ad: a.correct(c["hyp"], c["context"]).text)
        ablation[name] = {"technical_term_recall": agg["technical_term_recall"],
                          "exact_entity_accuracy": agg["exact_entity_accuracy"],
                          "false_substitution_total": agg["false_substitution_total"],
                          "wer": agg["wer"]}
    (OUT / "retrieval_ablation.json").write_text(json.dumps(ablation, indent=2), encoding="utf-8")

    # 4) Hard negatives (per pair, raw vs retrieval-corrected).
    pairs = {}
    for c in clips:
        if c["pair_id"]:
            pairs.setdefault(c["pair_id"], {})[c["pair_role"]] = c
    hn = {}
    for pid, roles in pairs.items():
        if "ordinary" in roles and "technical" in roles:
            def corr(c):
                return adapter.correct(c["hyp"], c["context"]).text
            o, t = roles["ordinary"], roles["technical"]
            hn[pid] = {
                "ordinary_raw": o["hyp"], "ordinary_corrected": corr(o),
                "ordinary_negs": o["negs"],
                "technical_raw": t["hyp"], "technical_corrected": corr(t),
                "technical_targets": t["targets"],
            }
    (OUT / "hard_negative_results.json").write_text(
        json.dumps({"pairs": list(hn), "analysis": hn}, indent=2), encoding="utf-8")

    # 5) Performance + determinism.
    sample = [(c["hyp"], c["context"]) for c in clips]
    for _ in range(20):
        for h, ctx in sample:
            adapter.correct(h, ctx)
    t0 = time.perf_counter()
    N = 50
    for _ in range(N):
        for h, ctx in sample:
            adapter.correct(h, ctx)
    per_utt_ms = (time.perf_counter() - t0) / (N * len(sample)) * 1000.0
    # retrieval-only latency.
    t0 = time.perf_counter()
    for _ in range(200):
        retriever.retrieve("postjsql", "developer", top_k=10)
    retr_ms = (time.perf_counter() - t0) / 200 * 1000.0
    # determinism x3.
    runs = []
    for _ in range(3):
        runs.append({c["id"]: adapter.correct(c["hyp"], c["context"]).text for c in clips})
    deterministic = runs[0] == runs[1] == runs[2]
    try:
        import psutil
        rss = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        rss = None
    perf = {
        "end_to_end_per_utterance_ms": round(per_utt_ms, 4),
        "retrieval_only_per_call_ms": round(retr_ms, 5),
        "index_load_file_bytes": IDX.stat().st_size,
        "process_rss_mib": rss,
        "deterministic_x3": deterministic,
    }
    (OUT / "performance.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    (OUT / "memory.json").write_text(json.dumps(
        {"process_rss_mib": rss, "index_file_bytes": IDX.stat().st_size,
         "metric": "process RSS via psutil (if available)"}, indent=2), encoding="utf-8")

    print("RECALL:", {k: round(v, 3) if isinstance(v, float) else v for k, v in recall.items()})
    print("RAW     :", "recall=%.3f exact=%.3f fsub=%d wer=%.3f" % (
        raw_agg["technical_term_recall"], raw_agg["exact_entity_accuracy"],
        raw_agg["false_substitution_total"], raw_agg["wer"]))
    print("9B MANUAL:", "recall=%.3f exact=%.3f fsub=%d wer=%.3f" % (
        manual_agg["technical_term_recall"], manual_agg["exact_entity_accuracy"],
        manual_agg["false_substitution_total"], manual_agg["wer"]))
    print("9C RETRIEVE:", "recall=%.3f exact=%.3f fsub=%d wer=%.3f" % (
        retr_agg["technical_term_recall"], retr_agg["exact_entity_accuracy"],
        retr_agg["false_substitution_total"], retr_agg["wer"]))
    print("perf:", perf)


if __name__ == "__main__":
    main()
