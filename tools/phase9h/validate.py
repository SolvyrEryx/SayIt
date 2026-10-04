"""Phase 9H — full-system validation + production-hardening harness.

Consolidates the Phase 9 intelligence stack and produces the final evidence:
  - benchmark arms 1-7 (raw ... full system) on the real 23-clip corpus
  - canonicalization metrics
  - false-positive audit
  - ordinary-language protection (email/chat)
  - failure modes (missing/corrupt index -> safe fallback)
  - long-run stability (repeated cycles, memory)
  - privacy/security AST audit across all 9x modules
  - knowledge versioning
  - determinism

Everything is EXPERIMENTAL (not wired into the production worker). The ASR path
is frozen. Emits artifacts/phase9h/*.json + the final report inputs.
"""

from __future__ import annotations

import ast
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

import metrics as M  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.candidate_ranker import CandidateRanker, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import CorrectorConfig, PostASRContextCorrector  # noqa: E402
from sayit.core.asr.post_context_pack import default_pack as manual_pack  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.adapter import RetrievalCorrectionAdapter  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.personalization import personalized_terms  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX9C = ROOT / "artifacts" / "phase9" / "9C" / "knowledge_index.json"
IDX9D = ROOT / "artifacts" / "phase9d" / "knowledge_index_domain.json"
IDX9E = ROOT / "artifacts" / "phase9e" / "knowledge_index_entity.json"
OUT = ROOT / "artifacts" / "phase9h"


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


def score(clips, transform):
    recs = []
    cx = ce = ct = 0
    for c in clips:
        hyp = transform(c)
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        ph_n, ph_d, _ = M.phrase_recall(hyp, c["phrases"] or c["targets"])
        fs_n, _ = M.false_technical_substitutions(hyp, c["negs"])
        for t in c["targets"]:
            ct += 1
            if M.term_present_exact(hyp, t):
                cx += 1
            if M.term_recognized_normalized(hyp, t) and M.term_present_exact(hyp, t):
                ce += 1
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
                     "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": ph_n,
                     "phrase_total": ph_d, "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    agg = M.aggregate(recs)
    agg["canonical_exact_accuracy"] = (cx / ct) if ct else None
    return agg


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    cfg, rcfg = CorrectorConfig(), RankerConfig()
    idx9c, idx9d, idx9e = (KnowledgeIndex.load(p) for p in (IDX9C, IDX9D, IDX9E))

    manual = PostASRContextCorrector(manual_pack(), cfg)
    c9c = RetrievalCorrectionAdapter(CandidateRetriever(idx9c), cfg, top_k=10)
    d9f = RankedRetrievalAdapter(CandidateRetriever(idx9c), CandidateRanker(rcfg), cfg, top_k=10)
    e9d = RankedRetrievalAdapter(CandidateRetriever(idx9d), CandidateRanker(rcfg), cfg, top_k=10)
    f9e = RankedRetrievalAdapter(CandidateRetriever(idx9e), CandidateRanker(rcfg), cfg, top_k=10)
    user_terms = personalized_terms([{"spoken": "my project x", "written": "ProjectXyz",
                                      "enabled": True, "usage_count": 3}])
    g9g = RankedRetrievalAdapter(CandidateRetriever(idx9e, user_terms=user_terms),
                                 CandidateRanker(rcfg), cfg, top_k=10)

    arms = {
        "1_raw": score(clips, lambda c: c["hyp"]),
        "2_9B": score(clips, lambda c: manual.correct(c["hyp"], c["context"]).text),
        "3_9C_9B": score(clips, lambda c: c9c.correct(c["hyp"], c["context"]).text),
        "4_9C_9F_9B": score(clips, lambda c: d9f.correct(c["hyp"], c["context"]).text),
        "5_9C_9D_9F_9B": score(clips, lambda c: e9d.correct(c["hyp"], c["context"]).text),
        "6_9C_9D_9E_9F_9B": score(clips, lambda c: f9e.correct(c["hyp"], c["context"]).text),
        "7_full_plus_personalization": score(clips, lambda c: g9g.correct(c["hyp"], c["context"]).text),
    }
    (OUT / "final_benchmark.json").write_text(json.dumps(arms, indent=2), encoding="utf-8")

    # Failure modes -> safe fallback (text unchanged, never raise).
    fm = {}
    fm["missing_index"] = RankedRetrievalAdapter(CandidateRetriever(None), top_k=10).correct(
        "run against postjsql", "developer").text
    # corrupt index file
    bad = OUT / "_corrupt.json"
    bad.write_text("{not valid", encoding="utf-8")
    try:
        KnowledgeIndex.load(bad)
        fm["corrupt_index_load"] = "LOADED (unexpected)"
    except Exception:
        fm["corrupt_index_load"] = "raised_and_caught_by_caller (safe)"
    bad.unlink(missing_ok=True)
    fm["empty_text"] = f9e.correct("", "developer").text
    fm["no_candidate_ordinary"] = f9e.correct("the weather is nice today", "email").text
    fm["safe_fallback_leaves_unchanged"] = (fm["no_candidate_ordinary"] == "the weather is nice today")
    (OUT / "failure_modes.json").write_text(json.dumps(fm, indent=2), encoding="utf-8")

    # Long-run stability: 50 cycles over the corpus, measure RSS growth.
    try:
        import psutil
        proc = psutil.Process()
        def rss():
            return proc.memory_info().rss / 1024 / 1024
    except Exception:
        rss = lambda: 0.0
    gc.collect()
    rss0 = rss()
    for _ in range(50):
        for c in clips:
            f9e.correct(c["hyp"], c["context"])
    gc.collect()
    rss1 = rss()
    (OUT / "stability.json").write_text(json.dumps({
        "cycles": 50, "clips_per_cycle": len(clips),
        "rss_before_mib": round(rss0, 1), "rss_after_mib": round(rss1, 1),
        "rss_growth_mib": round(rss1 - rss0, 1)}, indent=2), encoding="utf-8")

    # Determinism x3 on the full arm.
    runs = [{c["id"]: f9e.correct(c["hyp"], c["context"]).text for c in clips} for _ in range(3)]
    determinism = runs[0] == runs[1] == runs[2]

    # Latency of the full arm.
    sample = [(c["hyp"], c["context"]) for c in clips]
    ts = []
    for _ in range(30):
        for h, ctx in sample:
            t0 = time.perf_counter(); f9e.correct(h, ctx); ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    (OUT / "performance.json").write_text(json.dumps({
        "full_arm_median_ms": round(ts[len(ts) // 2], 3),
        "full_arm_p95_ms": round(ts[int(len(ts) * 0.95)], 3),
        "deterministic_x3": determinism,
        "index_bytes": {"9c": IDX9C.stat().st_size, "9d": IDX9D.stat().st_size, "9e": IDX9E.stat().st_size},
    }, indent=2), encoding="utf-8")

    # Privacy/security AST audit across all 9x intelligence modules.
    audit = {"modules": {}, "clean": True}
    mods = [
        ROOT / "src" / "sayit" / "core" / "asr" / "post_context.py",
        ROOT / "src" / "sayit" / "core" / "asr" / "post_context_pack.py",
        ROOT / "src" / "sayit" / "core" / "asr" / "candidate_ranker.py",
    ] + list((ROOT / "src" / "sayit" / "core" / "knowledge").glob("*.py"))
    forbidden_imports = ("urllib", "requests", "socket", "http", "subprocess", "ctypes", "pyperclip")
    forbidden_calls = ("eval", "exec", "system", "popen", "spawn")
    for m in mods:
        src = m.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imp, calls = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imp += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                imp.append(node.module or "")
            elif isinstance(node, ast.Call):
                f = node.func
                calls.append(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
        bad_i = [b for b in forbidden_imports if any(b in (x or "") for x in imp)]
        bad_c = [b for b in forbidden_calls if b in calls]
        clean = not bad_i and not bad_c
        audit["modules"][m.name] = {"clean": clean, "bad_imports": bad_i, "bad_calls": bad_c}
        audit["clean"] = audit["clean"] and clean
    (OUT / "privacy_security_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    # Knowledge versioning.
    (OUT / "knowledge_versions.json").write_text(json.dumps({
        "domain_pack_schema": "9d.1", "canonical_version": "9d.1", "entity_schema": "9e.1",
        "indexes": {"9c": "9c", "9d": "9d.1", "9e": "9e.1"},
        "production_sherpa_onnx": "1.12.21", "production_decoder": "greedy_search",
        "production_model": MODEL_ID}, indent=2), encoding="utf-8")

    for k, a in arms.items():
        print(k, "recall=%.3f exact=%.3f canon=%s phrase=%.3f fsub=%d ord=%.3f wer=%.3f" % (
            a["technical_term_recall"], a["exact_entity_accuracy"], a["canonical_exact_accuracy"],
            a["phrase_recall"], a["false_substitution_total"], a["ordinary_preservation"], a["wer"]))
    print("failure modes safe:", fm["safe_fallback_leaves_unchanged"], "| determinism:", determinism)
    print("privacy audit clean:", audit["clean"])
    print("stability growth MiB:", round(rss1 - rss0, 1))


if __name__ == "__main__":
    main()
