"""Phase 9D benchmark — domain packs + canonical-form quality.

Arms (same greedy ASR; raw-ASR correction metrics):
  A raw
  B 9B manual pack
  C 9C retrieval + 9B
  D 9C retrieval + 9F rank + 9B
  E 9C + 9D domain index + 9F + 9B
  F = E (domain index already carries canonical improvements)  [documented]

Adds canonical exact/case accuracy, cross-domain collision tests, pack-size
experiment (small/medium/large), hard negatives, determinism, perf.
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
from sayit.core.asr.candidate_ranker import CandidateRanker, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import CorrectorConfig, PostASRContextCorrector  # noqa: E402
from sayit.core.asr.post_context_pack import default_pack as manual_pack  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.adapter import RetrievalCorrectionAdapter  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.domain_packs import DOMAIN_PACKS, pack_terms  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX9C = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"
IDX9D = ROOT / "artifacts" / "phase9d" / "knowledge_index_domain.json"
OUT = ROOT / "artifacts" / "phase9d"


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
    canon_exact = 0
    canon_case = 0
    canon_total = 0
    for c in clips:
        hyp = transform(c)
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        ph_n, ph_d, _ = M.phrase_recall(hyp, c["phrases"] or c["targets"])
        fs_n, _ = M.false_technical_substitutions(hyp, c["negs"])
        # Canonical metrics: for each target, is the EXACT official form present
        # (canon_exact), and is the case correct given the term is recognized
        # case-insensitively (canon_case)?
        for t in c["targets"]:
            canon_total += 1
            if M.term_present_exact(hyp, t):
                canon_exact += 1
            if M.term_recognized_normalized(hyp, t) and M.term_present_exact(hyp, t):
                canon_case += 1
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n,
                     "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
                     "phrase_recalled": ph_n, "phrase_total": ph_d, "false_sub_count": fs_n,
                     "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    agg = M.aggregate(recs)
    agg["canonical_exact_accuracy"] = (canon_exact / canon_total) if canon_total else None
    agg["canonical_case_accuracy"] = (canon_case / canon_total) if canon_total else None
    return agg


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    idx9c = KnowledgeIndex.load(IDX9C)
    idx9d = KnowledgeIndex.load(IDX9D)
    cfg = CorrectorConfig()
    rcfg = RankerConfig()

    manual = PostASRContextCorrector(manual_pack(), cfg)
    c_adapter = RetrievalCorrectionAdapter(CandidateRetriever(idx9c), cfg, top_k=10)
    d_adapter = RankedRetrievalAdapter(CandidateRetriever(idx9c), CandidateRanker(rcfg), cfg, top_k=10)
    e_adapter = RankedRetrievalAdapter(CandidateRetriever(idx9d), CandidateRanker(rcfg), cfg, top_k=10)

    arms = {
        "A_raw": score(clips, lambda c: c["hyp"]),
        "B_9B_manual": score(clips, lambda c: manual.correct(c["hyp"], c["context"]).text),
        "C_9C_9B": score(clips, lambda c: c_adapter.correct(c["hyp"], c["context"]).text),
        "D_9C_9F_9B": score(clips, lambda c: d_adapter.correct(c["hyp"], c["context"]).text),
        "E_9C_9D_9F_9B": score(clips, lambda c: e_adapter.correct(c["hyp"], c["context"]).text),
    }
    arms["F_canonical"] = arms["E_9C_9D_9F_9B"]  # domain index already canonical
    (OUT / "benchmark.json").write_text(json.dumps(arms, indent=2), encoding="utf-8")

    # Pack-size experiment: small (web+databases), medium (+ai_ml+devops+security),
    # large (all domains).
    small = pack_terms(["web", "databases"])
    medium = pack_terms(["web", "databases", "ai_ml", "devops", "security"])
    large = pack_terms(None)
    sizes = {}
    for name, dterms in [("small", small), ("medium", medium), ("large", large)]:
        # Build an index from domain terms + the 9C base.
        base = KnowledgeIndex.load(IDX9C)
        combined = list(base._terms) + dterms  # type: ignore
        idx = KnowledgeIndex.from_terms(combined)
        ad = RankedRetrievalAdapter(CandidateRetriever(idx), CandidateRanker(rcfg), cfg, top_k=10)
        agg = score(clips, lambda c, a=ad: a.correct(c["hyp"], c["context"]).text)
        sizes[name] = {"domain_terms": len(dterms),
                       "technical_term_recall": agg["technical_term_recall"],
                       "exact_entity_accuracy": agg["exact_entity_accuracy"],
                       "canonical_exact_accuracy": agg["canonical_exact_accuracy"],
                       "false_substitution_total": agg["false_substitution_total"],
                       "ordinary_preservation": agg["ordinary_preservation"],
                       "wer": agg["wer"]}
    (OUT / "pack_size_experiment.json").write_text(json.dumps(sizes, indent=2), encoding="utf-8")

    # Hard negatives (ordinary preservation) on arm E.
    pairs = {}
    for c in clips:
        if c["pair_id"]:
            pairs.setdefault(c["pair_id"], {})[c["pair_role"]] = c
    hn = {}
    for pid, roles in pairs.items():
        if "ordinary" in roles and "technical" in roles:
            o, t = roles["ordinary"], roles["technical"]
            hn[pid] = {
                "ordinary_raw": o["hyp"], "ordinary_corrected": e_adapter.correct(o["hyp"], o["context"]).text,
                "ordinary_changed": o["hyp"] != e_adapter.correct(o["hyp"], o["context"]).text,
                "technical_corrected": e_adapter.correct(t["hyp"], t["context"]).text,
            }
    (OUT / "hard_negative_results.json").write_text(
        json.dumps({"pairs": list(hn), "analysis": hn}, indent=2), encoding="utf-8")

    # Collision tests: ordinary sentences containing ambiguous domain words.
    collisions = [
        ("i saw a spark in the sky", "chat"),
        ("the snowflake melted quickly", "chat"),
        ("please help me move this box", "email"),
        ("she went for a run this morning", "email"),
        ("the express train was late", "email"),
    ]
    coll = {}
    for text, ctx in collisions:
        out_text = e_adapter.correct(text, ctx).text
        coll[text] = {"context": ctx, "output": out_text, "changed": out_text != text}
    (OUT / "collision_analysis.json").write_text(json.dumps(coll, indent=2), encoding="utf-8")

    # Perf + determinism.
    sample = [(c["hyp"], c["context"]) for c in clips]
    for _ in range(10):
        for h, ctx in sample:
            e_adapter.correct(h, ctx)
    ts = []
    for _ in range(30):
        for h, ctx in sample:
            t0 = time.perf_counter(); e_adapter.correct(h, ctx); ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    runs = [{c["id"]: e_adapter.correct(c["hyp"], c["context"]).text for c in clips} for _ in range(3)]
    try:
        import psutil
        rss = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        rss = None
    (OUT / "performance.json").write_text(json.dumps({
        "arm_E_median_ms": round(ts[len(ts) // 2], 3), "arm_E_p95_ms": round(ts[int(len(ts) * 0.95)], 3),
        "index_bytes": IDX9D.stat().st_size, "process_rss_mib": rss,
        "deterministic_x3": runs[0] == runs[1] == runs[2]}, indent=2), encoding="utf-8")

    for k, a in arms.items():
        print(k, "recall=%.3f exact=%.3f canon_exact=%s phrase=%.3f fsub=%d ord=%.3f wer=%.3f" % (
            a["technical_term_recall"], a["exact_entity_accuracy"],
            a["canonical_exact_accuracy"], a["phrase_recall"], a["false_substitution_total"],
            a["ordinary_preservation"], a["wer"]))
    print("pack sizes:", {k: (v["exact_entity_accuracy"], v["false_substitution_total"]) for k, v in sizes.items()})
    print("collisions changed:", {k: v["changed"] for k, v in coll.items()})


if __name__ == "__main__":
    main()
