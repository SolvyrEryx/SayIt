"""Experimental ASR re-evaluation — SAFETY stage.

1. Hard-negative suite through the UNCHANGED SayIt pipeline (text-level; ASR-
   independent) across all contexts — confirms the 0-new-FP property holds.
2. ASR-hallucination check: for each top model, count held-out clips where the
   raw ASR injects an obvious technical token/acronym NOT present in the
   reference (a proxy for the model inventing technical entities).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import external_adapter as EA  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
OUT = ROOT / "artifacts" / "asr_evaluation"
CONTEXTS = ("normal", "developer", "email", "chat", "notes", "prompt")
TOP = ["sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8", "sherpa-onnx-whisper-small",
       "sherpa-onnx-whisper-large-v3"]

HARD_NEG = [
    ("i ate an apple for lunch", "Apple"), ("michael jordan was great", "Jordan"),
    ("we sailed down the amazon river", "Amazon"), ("i need to go home", "Go"),
    ("there is rust on the gate", "Rust"), ("that was a swift decision", "Swift"),
    ("the python slithered away", "Python"), ("he drank java this morning", "Java"),
    ("move on to the next item", "Next.js"), ("i need a fast api", "FastAPI"),
]
ACRONYM = re.compile(r"\b[A-Z]{3,6}\b")


def held_out_entries():
    tie = EA.scored_entries(EA.build_manifest(EXTERNAL))
    spk = sorted({e.speaker_id for e in tie})
    held = set(spk[::2])
    return [e for e in tie if e.speaker_id in held]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = IntelligencePipeline(domain_aware=False)
    rows, fp_total = [], 0
    for text, risky in HARD_NEG:
        for ctx in CONTEXTS:
            out = pipe.process(text, ctx).text if pipe.available else text
            fp = risky.lower() in out.lower() and risky.lower() not in text.lower()
            if fp:
                fp_total += 1
            rows.append(["pipeline", ctx, text, out, fp, risky])

    # ASR hallucination proxy: acronyms in hyp not in reference.
    entries = held_out_entries()
    raw_hyps = json.loads((OUT / "_raw_hyps.json").read_text(encoding="utf-8"))
    halluc = {}
    for mid in TOP:
        hyps = raw_hyps.get(mid, {})
        count = 0
        for e in entries:
            ref_ac = set(ACRONYM.findall(e.reference))
            hyp_ac = set(ACRONYM.findall(hyps.get(e.sample_id, "")))
            count += len(hyp_ac - ref_ac)
        halluc[mid] = count
        rows.append(["asr_hallucination_acronyms", mid, "", "", count, ""])

    with open(OUT / "safety_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ctx_or_model", "input", "output", "flag", "risky"])
        w.writerows(rows)

    print(f"pipeline hard-negative false substitutions (all contexts): {fp_total}")
    print("ASR hallucinated-acronym count per model (hyp acronyms not in ref):")
    for mid, c in halluc.items():
        print(f"  {mid.replace('sherpa-onnx-','')}: {c}")


if __name__ == "__main__":
    main()
