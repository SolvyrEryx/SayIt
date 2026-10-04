"""Experimental ASR re-evaluation — END-TO-END SayIt stage.

Takes the cached raw hyps from raw_benchmark.py and runs the UNCHANGED SayIt
intelligence pipeline on them, for the top candidates only. The intelligence,
knowledge index, ranker, and correction are identical across arms — ONLY the
ASR (i.e. the raw hyps) differs. Production is untouched (flag FALSE).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
import external_adapter as EA  # noqa: E402
import known_unseen as KU  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
OUT = ROOT / "artifacts" / "asr_evaluation"

# Top candidates to run end-to-end (production baseline + best alternatives).
TOP = [
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
    "sherpa-onnx-whisper-small",
    "sherpa-onnx-whisper-large-v3",
]


def held_out_entries():
    tie = EA.scored_entries(EA.build_manifest(EXTERNAL))
    spk = sorted({e.speaker_id for e in tie})
    held = set(spk[::2])
    return [e for e in tie if e.speaker_id in held]


def score(entries, hyps, pipe, known):
    recs, unseen = [], []
    lat = []
    for e in entries:
        raw = hyps.get(e.sample_id, "")
        ctx = e.metadata.get("context", "developer")
        if pipe is None:
            out = raw
        else:
            t0 = time.perf_counter()
            out = pipe.process(raw, ctx).text
            lat.append((time.perf_counter() - t0) * 1000.0)
        errs, words = M.wer(e.reference, out)
        tr_n, tr_d, _ = M.technical_term_recall(out, e.target_terms)
        ex_n, ex_d, _ = M.exact_entity_accuracy(out, e.target_terms)
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n,
                     "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
                     "phrase_recalled": 0, "phrase_total": 0, "false_sub_count": 0,
                     "has_negatives": False, "ordinary_preserved": None})
        for term in e.target_terms:
            if KU.classify_terms([term], known)[term] == "UNSEEN":
                t1, d1, _ = M.technical_term_recall(out, [term])
                unseen.append({"tech_recalled": t1, "tech_total": d1, "exact_count": 0,
                               "exact_total": 0, "errors": 0, "ref_words": 0,
                               "phrase_recalled": 0, "phrase_total": 0,
                               "false_sub_count": 0, "has_negatives": False,
                               "ordinary_preserved": None})
    a = M.aggregate(recs)
    u = M.aggregate(unseen) if unseen else {}
    lat.sort()
    return {"wer": round(a["wer"], 4),
            "technical_recall": round(a["technical_term_recall"], 4),
            "exact_entity": round(a["exact_entity_accuracy"], 4),
            "unseen_recall": round(u.get("technical_term_recall", 0.0), 4) if u else None,
            "intel_median_ms": round(lat[len(lat)//2], 1) if lat else None}


def main():
    entries = held_out_entries()
    known = KU.build_known_set()
    raw_hyps = json.loads((OUT / "_raw_hyps.json").read_text(encoding="utf-8"))
    pipe = IntelligencePipeline(domain_aware=False)  # current SayIt (ARM B style)

    results = {}
    for mid in TOP:
        if mid not in raw_hyps:
            continue
        hyps = raw_hyps[mid]
        results[mid] = {
            "raw_only": score(entries, hyps, None, known),
            "with_sayit": score(entries, hyps, pipe, known),
        }
    (OUT / "end_to_end_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for mid, r in results.items():
        short = mid.replace("sherpa-onnx-", "")
        print(f"\n== {short}")
        print(f"  raw      : recall={r['raw_only']['technical_recall']} "
              f"unseen={r['raw_only']['unseen_recall']} exact={r['raw_only']['exact_entity']} wer={r['raw_only']['wer']}")
        print(f"  +SayIt   : recall={r['with_sayit']['technical_recall']} "
              f"unseen={r['with_sayit']['unseen_recall']} exact={r['with_sayit']['exact_entity']} "
              f"wer={r['with_sayit']['wer']} intel_med={r['with_sayit']['intel_median_ms']}ms")


if __name__ == "__main__":
    main()
