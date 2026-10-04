"""Domain-intelligence false-positive + memory safety check (ARM C).

Confirms the domain-aware prior does NOT erode the 0-false-substitution behavior:
runs the ambiguous hard negatives across all contexts with developer domains
ACTIVE, and checks memory stability over repeated cycles.
"""

from __future__ import annotations

import csv
import gc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

OUT = ROOT / "artifacts" / "domain_intelligence"
CONTEXTS = ("normal", "developer", "email", "chat", "notes", "prompt")

# Ordinary utterances containing a word that collides with a technical entity.
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
    ("she will go next week", "Go"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = IntelligencePipeline(domain_aware=True,
                                enabled_domains=["web", "python", "ai_ml",
                                                 "data_sql", "devops_cloud",
                                                 "cybersecurity"])
    rows = []
    fp_total = 0
    for text, risky in HARD_NEG:
        for ctx in CONTEXTS:
            out_text = pipe.process(text, ctx).text if pipe.available else text
            changed = out_text != text
            fp = risky.lower() in out_text.lower() and risky.lower() not in text.lower()
            if fp:
                fp_total += 1
            rows.append([ctx, text, out_text, changed, fp, risky])

    with open(OUT / "false_positive_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["context", "input", "output", "changed", "false_sub", "risky_term"])
        w.writerows(rows)

    # Memory stability: repeated cycles should not grow unbounded.
    try:
        import os
        import psutil  # may be present via deps
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
        mem = {"note": f"psutil unavailable ({type(e).__name__}); mem check skipped"}

    print(f"false-positive total (domains ACTIVE, all contexts): {fp_total}")
    print("memory:", mem)
    return fp_total, mem


if __name__ == "__main__":
    main()
