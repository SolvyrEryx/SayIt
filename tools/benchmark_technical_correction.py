"""Benchmark the on-device technical-correction stage latency.

Measures the SAME stage the live pipeline brackets as
``correction_start``..``correction_end`` in transcription_worker.py — i.e.
``correct_transcript(...)`` (TechnicalCorrector: whitespace -> technical
aliases -> spelled acronyms -> structured formatting -> number/date rules).

It uses the existing privacy-safe timing system (PipelineTiming +
TimingAggregator) to report p50/p75/p90/p95/max in milliseconds per input
category:

  ordinary            — plain prose (correction should mostly abstain)
  technical           — registered technical terms / acronyms
  structured_technical— URLs/paths/versions/structured expressions
  difficult_technical — dense mix of the above in one utterance

Target: technical-correction p95 <= ~50 ms. Deterministic inputs; no network,
no model, no transcript logging beyond character counts.

Usage:
  python tools/benchmark_technical_correction.py [--runs 200] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sayit.core.asr.pipeline_timing import (  # noqa: E402
    PipelineTiming,
    TimingAggregator,
)
from sayit.core.transcript_processor import correct_transcript  # noqa: E402

# Reusable, non-benchmark-specific sample utterances per category. These contain
# NO hidden golden answers; they just exercise the corrector's code paths.
SAMPLES = {
    "ordinary": [
        "i went to the store this morning and bought some milk and bread",
        "the weather today is quite pleasant with a gentle breeze",
        "please remember to call your mother back this afternoon",
        "we should schedule the meeting for sometime next week",
        "i really enjoyed the book you recommended to me last month",
    ],
    "technical": [
        "we deployed the service using git hub actions and docker",
        "the ci slash cd pipeline runs the unit tests on every push",
        "configure the post gres database connection in the config file",
        "use java script and type script for the front end components",
        "the rest api returns json over https with oauth two tokens",
    ],
    "structured_technical": [
        "clone the repo from git hub dot com slash example slash project",
        "set the path to slash user slash local slash bin slash python",
        "bump the version to one point two point three before release",
        "send the report to admin at example dot com by friday",
        "the endpoint is api dot service dot io slash v two slash users",
    ],
    "difficult_technical": [
        "deploy the fast api service with post gres on ci slash cd to "
        "git hub dot com slash org slash repo at version two point one",
        "the type script client calls the rest api at api dot example dot com "
        "slash v three and stores the oauth two token in local storage",
        "run python slash scripts slash build dot py then push to git hub and "
        "trigger the docker build at ninety five percent coverage",
        "update the readme at slash docs slash index dot md and tag release "
        "three point four point zero on december thirty first",
        "configure nginx to proxy slash api to localhost colon eight thousand "
        "and enable https with the cert at slash etc slash ssl",
    ],
}


def bench_category(name: str, samples: list[str], runs: int) -> dict:
    agg = TimingAggregator()
    job = 0
    # Warm-up (alias table build / regex compile caches) excluded from stats.
    for s in samples:
        correct_transcript(s)
    for _ in range(runs):
        for s in samples:
            job += 1
            t = PipelineTiming(job_id=job)
            t.mark("correction_start")
            res = correct_transcript(s)
            t.mark("correction_end")
            t.final_char_count = len(res.text)
            agg.add(t)
    stats = agg.stats().get("correction_overhead", {})
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    results = {}
    print(f"Technical-correction stage benchmark (runs={args.runs} per sample)\n")
    print(
        f"{'category':22s} {'n':>6} {'p50':>8} {'p75':>8} {'p90':>8} {'p95':>8} {'max':>8}  (ms)"
    )
    for name, samples in SAMPLES.items():
        stats = bench_category(name, samples, args.runs)
        results[name] = stats
        print(
            f"{name:22s} {stats.get('n',0):6d} "
            f"{stats.get('p50',0):8.2f} {stats.get('p75',0):8.2f} "
            f"{stats.get('p90',0):8.2f} {stats.get('p95',0):8.2f} "
            f"{stats.get('max',0):8.2f}"
        )

    worst_p95 = max((s.get("p95", 0) for s in results.values()), default=0)
    target = 50.0
    print(
        f"\nworst-category p95 = {worst_p95:.2f} ms  (target <= {target:.0f} ms)  "
        f"-> {'PASS' if worst_p95 <= target else 'OVER TARGET'}"
    )

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
