"""Phase 9G benchmark — explicit personalization as a ranking prior."""

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
from sayit.core.asr.post_context import CorrectorConfig  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.personalization import PersonalizationStore, personalized_terms  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX9E = ROOT / "artifacts" / "phase9e" / "knowledge_index_entity.json"
OUT = ROOT / "artifacts" / "phase9g"


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


def adapter(index, user_terms):
    retr = CandidateRetriever(index, user_terms=user_terms)
    return RankedRetrievalAdapter(retr, CandidateRanker(RankerConfig()), CorrectorConfig(), top_k=10)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    idx = KnowledgeIndex.load(IDX9E)

    # Explicit user vocabulary (as if the user had used Remember Correction).
    user_vocab = [
        {"spoken": "my project x", "written": "ProjectXyz", "enabled": True,
         "category": "project", "usage_count": 3},
        {"spoken": "acme corp", "written": "ACME Corp", "enabled": True,
         "category": "org", "usage_count": 1},
    ]
    user_terms = personalized_terms(user_vocab)

    arms = {
        "baseline_no_personalization": score(clips, adapter(idx, [])),
        "with_explicit_vocab": score(clips, adapter(idx, user_terms)),
    }
    (OUT / "benchmark.json").write_text(json.dumps(arms, indent=2), encoding="utf-8")

    # Personalized recovery: a user term should be recoverable from its spoken
    # form once explicitly saved — but still subject to 9F gates.
    ad = adapter(idx, user_terms)
    recov = {}
    for text, ctx, want in [("deploy my project x now", "developer", "ProjectXyz"),
                            ("email acme corp today", "developer", "ACME Corp")]:
        out_text = ad.correct(text, ctx).text
        recov[text] = {"want": want, "output": out_text, "recovered": want in out_text}
    (OUT / "personalization_recovery.json").write_text(json.dumps(recov, indent=2), encoding="utf-8")

    # Conflict / lifecycle tests.
    lifecycle = {}
    store = PersonalizationStore(list(user_vocab))
    lifecycle["inspect_count"] = len(store.inspect())
    lifecycle["disabled"] = store.disable("acme corp")
    lifecycle["enabled_terms_after_disable"] = len(store.enabled_terms())
    lifecycle["deleted"] = store.delete("my project x")
    lifecycle["after_delete_count"] = len(store.inspect())
    store.clear()
    lifecycle["after_clear_count"] = len(store.inspect())
    # Zero-personalization fallback == baseline.
    lifecycle["zero_personalization_equals_baseline"] = (
        score(clips, adapter(idx, [])) == arms["baseline_no_personalization"])
    # Conflict: two entries same spoken form, different written -> deterministic.
    conflict_vocab = [
        {"spoken": "my db", "written": "PostgreSQL", "enabled": True, "usage_count": 1},
        {"spoken": "my db", "written": "MongoDB", "enabled": True, "usage_count": 1},
    ]
    ct = personalized_terms(conflict_vocab)
    cad = adapter(idx, ct)
    o1 = cad.correct("connect to my db", "developer").text
    o2 = cad.correct("connect to my db", "developer").text
    lifecycle["conflict_deterministic"] = (o1 == o2)
    lifecycle["conflict_output"] = o1
    # Disabled entry must NOT contribute.
    disabled_vocab = [{"spoken": "my project x", "written": "ProjectXyz",
                       "enabled": False, "usage_count": 5}]
    dad = adapter(idx, personalized_terms(disabled_vocab))
    lifecycle["disabled_entry_inactive"] = ("ProjectXyz" not in
                                            dad.correct("deploy my project x now", "developer").text)
    (OUT / "lifecycle_conflict.json").write_text(json.dumps(lifecycle, indent=2), encoding="utf-8")

    # Perf + determinism.
    adp = adapter(idx, user_terms)
    sample = [(c["hyp"], c["context"]) for c in clips]
    for _ in range(10):
        for h, ctx in sample:
            adp.correct(h, ctx)
    ts = []
    for _ in range(30):
        for h, ctx in sample:
            t0 = time.perf_counter(); adp.correct(h, ctx); ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    runs = [{c["id"]: adp.correct(c["hyp"], c["context"]).text for c in clips} for _ in range(3)]
    try:
        import psutil
        rss = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        rss = None
    (OUT / "performance.json").write_text(json.dumps({
        "median_ms": round(ts[len(ts) // 2], 3), "p95_ms": round(ts[int(len(ts) * 0.95)], 3),
        "process_rss_mib": rss, "deterministic_x3": runs[0] == runs[1] == runs[2]}, indent=2), encoding="utf-8")

    for k, a in arms.items():
        print(k, "recall=%.3f exact=%.3f fsub=%d ord=%.3f wer=%.3f" % (
            a["technical_term_recall"], a["exact_entity_accuracy"], a["false_substitution_total"],
            a["ordinary_preservation"], a["wer"]))
    print("personalized recovery:", {k: v["recovered"] for k, v in recov.items()})
    print("lifecycle:", lifecycle)


if __name__ == "__main__":
    main()
