"""Phase 9E — build entity-enhanced index + conservative entity benchmark."""

from __future__ import annotations

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
from sayit.core.asr.candidate_ranker import CandidateRanker, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import CorrectorConfig  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.models import KnowledgeTerm, normalize_text  # noqa: E402
from sayit.core.knowledge.entities import ENTITY_PACKS, entity_stats, entity_terms  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX9D = ROOT / "artifacts" / "phase9d" / "knowledge_index_domain.json"
OUT = ROOT / "artifacts" / "phase9e"


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
                    "phrases": e.get("phrase_terms", []), "context": context_for(e)})
    return out


def score(clips, ad):
    recs = []
    for c in clips:
        hyp = ad.correct(c["hyp"], c["context"]).text
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        ph_n, ph_d, _ = M.phrase_recall(hyp, c["phrases"] or c["targets"])
        fs_n, _ = M.false_technical_substitutions(hyp, c["negs"])
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
                     "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": ph_n,
                     "phrase_total": ph_d, "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    return M.aggregate(recs)


def build_entity_index():
    base = KnowledgeIndex.load(IDX9D)
    # Merge entities; existing domain canonical wins on casing (same policy).
    by_norm = {normalize_text(t.canonical): t for t in base._terms}  # type: ignore
    order = [normalize_text(t.canonical) for t in base._terms]  # type: ignore
    for et in entity_terms():
        k = normalize_text(et.canonical)
        if k not in by_norm:
            by_norm[k] = et
            order.append(k)
        else:
            ex = by_norm[k]
            variants = tuple(dict.fromkeys([*ex.spoken_variants, *et.spoken_variants]))
            # carry entity ambiguity metadata if the base lacked it
            meta = dict(ex.metadata)
            meta.setdefault("ambiguity_class", et.metadata.get("ambiguity_class", "none"))
            by_norm[k] = KnowledgeTerm(canonical=ex.canonical, spoken_variants=variants,
                                       category=ex.category, domain=ex.domain,
                                       source=ex.source + "+entity", relevance=max(ex.relevance, et.relevance),
                                       metadata=meta)
    return KnowledgeIndex.from_terms([by_norm[k] for k in order])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    cfg, rcfg = CorrectorConfig(), RankerConfig()
    idx9d = KnowledgeIndex.load(IDX9D)
    idx9e = build_entity_index()
    idx9e.save(OUT / "knowledge_index_entity.json")

    d_adapter = RankedRetrievalAdapter(CandidateRetriever(idx9d), CandidateRanker(rcfg), cfg, top_k=10)
    e_adapter = RankedRetrievalAdapter(CandidateRetriever(idx9e), CandidateRanker(rcfg), cfg, top_k=10)

    arms = {
        "9F_9D": score(clips, d_adapter),       # 9C+9D+9F+9B (entity OFF)
        "9F_9D_9E": score(clips, e_adapter),    # + entities
    }
    (OUT / "benchmark.json").write_text(json.dumps(arms, indent=2), encoding="utf-8")

    # Entity hard negatives: ambiguous proper/ordinary names in ordinary context
    # must be LEFT UNCHANGED; a clear technical/organization context may correct.
    hard = [
        ("i ate an apple for lunch", "chat", "Apple"),
        ("michael jordan was a great player", "chat", "Jordan"),
        ("we sailed down the amazon river", "chat", "Amazon"),
        ("i need to go to the store", "chat", "Go"),
        ("that was a swift decision", "email", "Swift"),
        ("there is rust on the gate", "email", "Rust"),
        ("the python slithered away", "chat", "Python"),
    ]
    hn = {}
    for text, ctx, risky in hard:
        out_text = e_adapter.correct(text, ctx).text
        hn[text] = {"context": ctx, "risky_entity": risky, "output": out_text,
                    "changed": out_text != text,
                    "false_substitution": risky in out_text}
    (OUT / "hard_negative_results.json").write_text(
        json.dumps({"cases": hn,
                    "false_sub_count": sum(1 for v in hn.values() if v["false_substitution"])},
                   indent=2), encoding="utf-8")

    # Positive entity recovery in strong context.
    pos = [
        ("we call open ai from the worker", "developer", "OpenAI"),
        ("push to git hub", "developer", "GitHub"),
        ("deploy with kubernetes", "developer", "Kubernetes"),
    ]
    recov = {}
    for text, ctx, want in pos:
        out_text = e_adapter.correct(text, ctx).text
        recov[text] = {"want": want, "output": out_text, "recovered": want in out_text}
    (OUT / "entity_recovery.json").write_text(json.dumps(recov, indent=2), encoding="utf-8")

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
        "arm_9E_median_ms": round(ts[len(ts) // 2], 3), "arm_9E_p95_ms": round(ts[int(len(ts) * 0.95)], 3),
        "index_bytes": (OUT / "knowledge_index_entity.json").stat().st_size,
        "process_rss_mib": rss, "deterministic_x3": runs[0] == runs[1] == runs[2]}, indent=2), encoding="utf-8")
    (OUT / "entity_statistics.json").write_text(json.dumps(entity_stats(), indent=2), encoding="utf-8")

    manifest = f"""# Phase 9E Entity Source Manifest

Build date: {datetime.now(timezone.utc).isoformat()}
Schema version: 9e.1

## Entity packs (curated, local, inert)
"""
    for name, ents in ENTITY_PACKS.items():
        manifest += f"- **{name}**: {len(ents)} entities\n"
    manifest += """
## Potential build-time sources (NOT runtime; bounded curated subset shipped)
- OSMNames (geographic names) — documented as a future build-time source;
  the full world gazetteer is NOT imported (candidate explosion + ordinary-word
  collisions). A bounded curated real location subset is used instead.
- Authoritative org/project metadata — curated real entities.

## Conservatism
Ambiguous entities (Apple/Jordan/Amazon/Go/Swift/Rust/Python) are flagged
ordinary/proper; the 9F ranker applies an ambiguity penalty so they are left
unchanged without strong context. No runtime network. No invented canonicals.
"""
    (OUT / "ENTITY_SOURCE_MANIFEST.md").write_text(manifest, encoding="utf-8")

    for k, a in arms.items():
        print(k, "recall=%.3f exact=%.3f phrase=%.3f fsub=%d ord=%.3f wer=%.3f" % (
            a["technical_term_recall"], a["exact_entity_accuracy"], a["phrase_recall"],
            a["false_substitution_total"], a["ordinary_preservation"], a["wer"]))
    print("entity hard-neg false subs:", sum(1 for v in hn.values() if v["false_substitution"]),
          "/", len(hn))
    for t, v in hn.items():
        print("  ", v["false_substitution"], "|", repr(v["output"][:50]))
    print("entity recovery:", {k: v["recovered"] for k, v in recov.items()})


if __name__ == "__main__":
    main()
