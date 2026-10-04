"""Domain-intelligence evaluation — ARM A (raw) / B (current SayIt) / C (domain-aware).

Honest, held-out, speaker-split evaluation of whether the domain-aware prior
improves UNSEEN technical recall while preserving the 0-false-substitution
behavior measured on 120 real TIE speakers.

Hard rules enforced here:
- ASR is identical across arms (one greedy Parakeet pass; arms differ only in
  post-text intelligence).
- Deterministic dev/held-out split by SPEAKER (a speaker is never in both).
- Known/unseen is computed against the knowledge-index HASH captured BEFORE the
  evaluation (recorded in the output), and the classifier is read-only.
- The held-out set is NEVER used to construct domain packs or tune thresholds.
- Nothing is written into the knowledge base.
"""

from __future__ import annotations

import csv
import hashlib
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
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
import external_adapter as EA  # noqa: E402
import known_unseen as KU  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
A2_LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
A2_CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
PACKAGED_INDEX = ROOT / "src" / "sayit" / "core" / "knowledge" / "data" / "knowledge_index.json"
OUT = ROOT / "artifacts" / "domain_coverage"

# Domains enabled for ARM C (developer-oriented; this is a *configuration*, not
# derived from the held-out set).
ARM_C_DOMAINS = ["web", "python", "ai_ml", "data_sql", "devops_cloud", "cybersecurity",
                 "aerospace", "control_systems", "chemistry", "electronics", "mathematics"]


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def index_hash() -> str:
    if not PACKAGED_INDEX.exists():
        return "none"
    return hashlib.sha256(PACKAGED_INDEX.read_bytes()).hexdigest()[:16]


def split_by_speaker(entries, held_fraction=0.5):
    """Deterministic dev/held-out split: sort speakers, alternate assignment so
    disciplines/regions spread across both halves; a speaker is in exactly one."""
    speakers = sorted({e.speaker_id for e in entries})
    held = set(speakers[::2])  # every other speaker -> held-out (deterministic)
    dev = {s for s in speakers if s not in held}
    dev_e = [e for e in entries if e.speaker_id in dev]
    held_e = [e for e in entries if e.speaker_id in held]
    return dev_e, held_e


def transcribe(entries):
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    hyps = {}
    for e in entries:
        if e.audio_status != "ok":
            continue
        d, sr, _ = read_wav(Path(e.audio_path))
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        hyps[e.sample_id] = s.result.text.strip()
    return hyps


def score_arm(entries, hyps, pipe, known, latencies=None):
    recs, per_speaker = [], {}
    known_recs, unseen_recs = [], []
    for e in entries:
        raw = hyps.get(e.sample_id, "")
        ctx = (e.metadata.get("context") or "developer")
        if pipe is None:
            hyp = raw
        else:
            t0 = time.perf_counter()
            hyp = pipe.process(raw, ctx).text
            if latencies is not None:
                latencies.append((time.perf_counter() - t0) * 1000.0)
        errs, words = M.wer(e.reference, hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, e.target_terms)
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, e.target_terms)
        negs = e.metadata.get("negatives", [])
        fs_n, _ = M.false_technical_substitutions(hyp, negs)
        rec = {"errors": errs, "ref_words": words, "tech_recalled": tr_n,
               "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
               "phrase_recalled": 0, "phrase_total": 0, "false_sub_count": fs_n,
               "has_negatives": bool(negs),
               "ordinary_preserved": (fs_n == 0) if negs else None}
        recs.append(rec)
        # KNOWN/UNSEEN per-term buckets.
        for term in e.target_terms:
            cls = "known" if KU.classify_terms([term], known)[term] == "KNOWN" else "unseen"
            tr1, td1, _ = M.technical_term_recall(hyp, [term])
            ex1, exd1, _ = M.exact_entity_accuracy(hyp, [term])
            b = {"tech_recalled": tr1, "tech_total": td1, "exact_count": ex1,
                 "exact_total": exd1, "errors": 0, "ref_words": 0, "phrase_recalled": 0,
                 "phrase_total": 0, "false_sub_count": 0, "has_negatives": False,
                 "ordinary_preserved": None}
            (known_recs if cls == "known" else unseen_recs).append(b)
        sp = per_speaker.setdefault(e.speaker_id, [])
        sp.append((errs, words))
    agg = M.aggregate(recs) if recs else {}
    known_agg = M.aggregate(known_recs) if known_recs else {}
    unseen_agg = M.aggregate(unseen_recs) if unseen_recs else {}
    return agg, known_agg, unseen_agg, per_speaker


def corpus_entries():
    """23-clip SayIt corpus as external-adapter entries (dev regression)."""
    out = []
    for e in json.loads(A2_LABELS.read_text(encoding="utf-8")):
        if e.get("needs_recording"):
            continue
        wav = e.get("wav", e["id"] + ".wav")
        p = next((b / wav for b in (A2_CORPUS, EVAL) if (b / wav).exists()), None)
        if p is None:
            continue
        role, cat = e.get("pair_role"), e.get("category")
        ctx = "developer" if (role == "technical" or cat in ("technical", "multiword", "mixed")) else "email"
        out.append(EA.ManifestEntry(
            sample_id=f"sayit_{e['id']}", speaker_id="S1", reference=e["reference"],
            source="sayit_corpus", audio_path=str(p), audio_status="ok",
            metadata={"context": ctx, "negatives": e.get("negative_terms", [])},
            target_terms=e.get("target_terms", [])))
    out.sort(key=lambda x: x.sample_id)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pre_hash = index_hash()
    known = KU.build_known_set()

    tie = EA.scored_entries(EA.build_manifest(EXTERNAL))
    corpus = corpus_entries()
    dev_tie, held_tie = split_by_speaker(tie) if tie else ([], [])

    pipe_b = IntelligencePipeline(domain_aware=False)
    pipe_c = IntelligencePipeline(domain_aware=True, enabled_domains=ARM_C_DOMAINS)

    results = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "index_hash_pre_eval": pre_hash, "arm_c_domains": ARM_C_DOMAINS,
               "datasets": {}}
    speaker_rows = []

    for name, entries in (("sayit_corpus", corpus), ("tie_heldout", held_tie),
                          ("tie_dev", dev_tie)):
        if not entries:
            continue
        hyps = transcribe(entries)
        ku = KU.summarize([e.target_terms for e in entries], known)
        lat_c = []
        a, ak, au, _ = score_arm(entries, hyps, None, known)
        b, bk, bu, bsp = score_arm(entries, hyps, pipe_b, known)
        c, ck, cu, csp = score_arm(entries, hyps, pipe_c, known, latencies=lat_c)
        lat_c.sort()
        results["datasets"][name] = {
            "clips": len(entries), "speakers": len({e.speaker_id for e in entries}),
            "known_unseen": {k: ku[k] for k in ("total_terms", "known", "unseen",
                                                "known_fraction", "unseen_fraction")},
            "arm_A_raw": a, "arm_B_current": b, "arm_C_domain": c,
            "known_terms": {"A": ak, "B": bk, "C": ck},
            "unseen_terms": {"A": au, "B": bu, "C": cu},
            "latency_c_ms": {"median": round(lat_c[len(lat_c)//2], 2) if lat_c else None,
                             "p95": round(lat_c[int(len(lat_c)*0.95)-1], 2) if lat_c else None},
        }
        for sp in sorted(bsp):
            def wer_of(spd):
                er = sum(x[0] for x in spd.get(sp, [])); wd = sum(x[1] for x in spd.get(sp, []))
                return round(er/wd, 4) if wd else 0.0
            speaker_rows.append([name, sp, len(bsp[sp]), wer_of(bsp), wer_of(csp)])

    (OUT / "benchmark_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with open(OUT / "speaker_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "speaker_id", "clips", "wer_B", "wer_C"])
        w.writerows(speaker_rows)
    assert index_hash() == pre_hash, "index mutated during eval!"

    for name, d in results["datasets"].items():
        print(f"\n== {name}: {d['clips']} clips / {d['speakers']} spk | unseen={d['known_unseen']['unseen_fraction']}")
        for arm in ("arm_A_raw", "arm_B_current", "arm_C_domain"):
            m = d[arm]
            print(f"  {arm}: recall={m.get('technical_term_recall')} exact={m.get('exact_entity_accuracy')} "
                  f"wer={m.get('wer')} fsub={m.get('false_substitution_total')}")
        print(f"  UNSEEN recall A/B/C: {d['unseen_terms']['A'].get('technical_term_recall')} / "
              f"{d['unseen_terms']['B'].get('technical_term_recall')} / "
              f"{d['unseen_terms']['C'].get('technical_term_recall')}")
    print("\nindex_hash stable:", index_hash() == pre_hash)


if __name__ == "__main__":
    main()
