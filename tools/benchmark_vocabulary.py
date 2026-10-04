"""Phase 6J vocabulary-layer latency benchmark (local, deterministic).

Measures the real processing time of ``apply_user_vocabulary`` as the number of
user entries grows (10 / 100 / 500 / 1000). Uses synthetic entries and a fixed
sample sentence; no ASR, no network, no transcript storage. Writes results to
artifacts/phase6/model-benchmark/phase6j-vocab-latency.json.

Usage:
    uv run python tools/benchmark_vocabulary.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sayit.core.transcript_processor import (  # noqa: E402
    VocabularyEntry,
    apply_user_vocabulary,
)

ART = Path("artifacts/phase6/model-benchmark")

# A representative short/medium dictated sentence (what the layer runs on).
_SAMPLE = (
    "ship the next js app with open ai and fast api then push to git hub "
    "and run the ci cd pipeline against the staging database before noon"
)


def _make_entries(n: int) -> list:
    """Build n deterministic, non-overlapping synthetic entries plus a few real
    multi-word ones so the measurement reflects realistic matching work."""
    entries = [
        VocabularyEntry(spoken="next js", written="Next.js"),
        VocabularyEntry(spoken="open ai", written="OpenAI"),
        VocabularyEntry(spoken="fast api", written="FastAPI"),
    ]
    for i in range(max(0, n - len(entries))):
        entries.append(
            VocabularyEntry(spoken=f"term{i} phrase", written=f"Term{i}")
        )
    return entries[:n]


def _measure(entries: list, iterations: int = 200) -> dict:
    # Warm-up.
    apply_user_vocabulary(_SAMPLE, entries)
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        apply_user_vocabulary(_SAMPLE, entries)
        times.append(time.perf_counter() - t0)
    times.sort()
    return {
        "entries": len(entries),
        "iterations": iterations,
        "median_ms": round(times[len(times) // 2] * 1000, 4),
        "p95_ms": round(times[int(len(times) * 0.95)] * 1000, 4),
        "max_ms": round(times[-1] * 1000, 4),
    }


def main():
    ART.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in (10, 100, 500, 1000):
        row = _measure(_make_entries(n))
        rows.append(row)
        print(
            f"entries={row['entries']:5d} median={row['median_ms']}ms "
            f"p95={row['p95_ms']}ms max={row['max_ms']}ms"
        )
    out = ART / "phase6j-vocab-latency.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
