"""Phase 10 (wordfreq experiment) — isolated ordinary-language frequency prior.

Hypothesis: an ordinary-language frequency signal can further suppress the one
residual false substitution ("fast api" -> FastAPI in developer/prompt context)
WITHOUT losing technical recall. This is an ISOLATED EXPERIMENT:

- It is NOT wired into the production ranker or pipeline.
- It introduces NO new runtime dependency: rather than depend on the `wordfreq`
  pip package (a historical-snapshot dataset), it uses a tiny self-contained
  table of the most common English words. If `wordfreq` were later shown to
  help materially, swapping this table for it is a one-line change — but that is
  only justified by evidence (which this experiment produces).
- Deterministic, fail-safe.

The frequency prior yields a penalty in [0, max_penalty] applied to a candidate
when the OBSERVED span is composed of common ordinary words — i.e. the span is
likely ordinary language, so forcing a technical entity is riskier.
"""

from __future__ import annotations

import re
from typing import Optional

# Tiny self-contained ordinary-English frequency table (rank-based). Values are
# an approximate "commonness" in [0,1] (1 = extremely common). This is a small
# curated set covering the ordinary words that collide with SayIt's technical
# entities + high-frequency function words. NOT the wordfreq dataset.
_COMMON = {
    "the": 1.0, "a": 1.0, "an": 0.98, "to": 1.0, "of": 1.0, "and": 1.0,
    "for": 0.99, "in": 1.0, "on": 0.98, "is": 0.99, "it": 0.98, "i": 1.0,
    "need": 0.9, "service": 0.85, "fast": 0.9, "open": 0.9, "next": 0.9,
    "go": 0.95, "swift": 0.75, "rust": 0.7, "python": 0.6, "react": 0.8,
    "apple": 0.85, "amazon": 0.8, "jordan": 0.7, "spark": 0.75, "express": 0.85,
    "web": 0.85, "auth": 0.5, "flow": 0.8, "tensor": 0.2, "node": 0.75,
    "run": 0.9, "store": 0.85, "api": 0.6,
}


def _tokens(s: str):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()


def ordinary_frequency(span: str) -> float:
    """Return the mean commonness of the span's tokens in [0,1]. Tokens not in
    the table are treated as rare (0.0). A high value => the span reads as
    ordinary English."""
    toks = _tokens(span)
    if not toks:
        return 0.0
    return sum(_COMMON.get(t, 0.0) for t in toks) / len(toks)


class FrequencyPrior:
    """Experimental scorer feature. Produces a penalty to subtract from a
    candidate's rank score when the observed span looks like ordinary language.

    ``max_penalty`` caps the effect. ``threshold`` is the mean-commonness above
    which the penalty engages. Deterministic and fail-safe."""

    def __init__(self, max_penalty: float = 0.15, threshold: float = 0.7,
                 enabled: bool = True):
        self.max_penalty = max_penalty
        self.threshold = threshold
        self.enabled = enabled

    def penalty(self, observed_span: str) -> float:
        if not self.enabled:
            return 0.0
        try:
            freq = ordinary_frequency(observed_span)
            if freq < self.threshold:
                return 0.0
            # Scale penalty linearly from 0 at threshold to max_penalty at 1.0.
            span = max(1e-6, 1.0 - self.threshold)
            return round(self.max_penalty * (freq - self.threshold) / span, 5)
        except Exception:
            return 0.0
