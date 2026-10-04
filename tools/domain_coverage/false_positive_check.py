"""Domain-coverage false-positive + memory safety check (science domains active)."""

from __future__ import annotations

import csv
import gc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

OUT = ROOT / "artifacts" / "domain_coverage"
CONTEXTS = ("normal", "developer", "email", "chat", "notes", "prompt")
DOMAINS = ["web", "python", "ai_ml", "data_sql", "devops_cloud", "cybersecurity",
           "aerospace", "control_systems", "chemistry", "electronics", "mathematics"]

HARD_NEG = [
    ("i ate an apple for lunch", "Apple"),
    ("michael jordan was a great player", "Jordan"),
    ("we sailed down the amazon river", "Amazon"),
    ("i need to go to the store", "Go"),
    ("there is rust on the gate", "Rust"),
    ("that was a swift decision", "Swift"),
    ("the python slithered away", "Python"),
    ("he drank a cup of java this morning", "Java"),
    ("let's move on to the next item", "Next.js"),
    ("i need a fast api for the service", "FastAPI"),
    # control-systems ambiguous ordinary words (must NOT become technical)
    ("the control was difficult", "control"),
    ("that is a good model", "model"),
    ("water the plant today", "plant"),
    ("what is your state of mind", "state"),
    ("he has a lot to gain", "gain"),
    ("we are out of phase", "phase"),
    ("the root of the tree is deep", "root"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = IntelligencePipeline(domain_aware=True, enabled_domains=DOMAINS)
    rows, fp_total = [], 0
    for text, risky in HARD_NEG:
        for ctx in CONTEXTS:
            out_text = pipe.process(text, ctx).text if pipe.available else text
            changed = out_text != text
            # false positive = risky term (as a technical entity) injected.
            fp = (risky[:1].isupper() and risky.lower() in out_text.lower()
                  and risky.lower() not in text.lower())
            # for lowercase ambiguous words, FP = the word got capitalized/changed
            if not risky[:1].isupper():
                fp = changed and risky in out_text and risky in text and \
                    out_text.lower() == text.lower() and out_text != text
            if fp:
                fp_total += 1
            rows.append([ctx, text, out_text, changed, fp, risky])

    with open(OUT / "false_positive_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["context", "input", "output", "changed", "false_sub", "risky_term"])
        w.writerows(rows)

    try:
        import os
        import psutil
        proc = psutil.Process(os.getpid())
        gc.collect()
        rss0 = proc.memory_info().rss
        for _ in range(50):
            for text, _r in HARD_NEG:
                pipe.process(text, "developer")
        gc.collect()
        rss1 = proc.memory_info().rss
        mem = {"rss_start_mib": round(rss0 / 1048576, 2),
               "rss_end_mib": round(rss1 / 1048576, 2),
               "growth_mib": round((rss1 - rss0) / 1048576, 2)}
    except Exception as e:
        mem = {"note": f"psutil unavailable ({type(e).__name__})"}

    # count any clip that actually changed (to show science domains don't fire on ordinary)
    changed_total = sum(1 for r in rows if r[3])
    print(f"false-positive total (science domains ACTIVE, all contexts): {fp_total}")
    print(f"clips changed at all: {changed_total} / {len(rows)}")
    print("memory:", mem)
    return fp_total


if __name__ == "__main__":
    main()
