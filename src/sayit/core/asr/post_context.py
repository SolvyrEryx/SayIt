"""Phase 9B — isolated post-ASR contextual candidate correction (PROOF-OF-CAPABILITY).

This module tests a single question: given a SMALL set of relevant technical
candidates, can deterministic post-ASR correction recover greedy-Parakeet errors
(e.g. "postjsql" -> "PostgreSQL") WITHOUT turning ordinary speech into technical
entities (e.g. "fast API" must stay "fast API")?

It is NOT wired into the production worker. It owns no ASR, recording, model,
UI, clipboard, or context detection — a caller passes in the raw transcript and
an optional context profile string. It is pure, deterministic, explainable, and
fail-safe (returns the input unchanged on any uncertainty or error).

Key design fact (measured in 9B.1): alnum-normalized edit similarity scores the
DANGEROUS ordinary->technical collapses at ~1.0 ("fast api"->"fastapi"), while
genuinely recoverable mangled tokens score lower ("postjsql"->"postgresql"=0.78).
So similarity alone cannot separate them. The corrector therefore:
  - treats a raw span that is already a clean ordinary English phrase as
    PROTECTED (only correctable under strong technical context + margin), and
  - treats a non-word mangled span (not ordinary English) as eligible for
    correction when similarity + margin + context gates pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

# A tiny ordinary-English guard list: words that, when they make up the raw
# span, signal ordinary language. This is NOT a lexicon integration (that is a
# future phase) — it is a small bounded guard for the hard-negative forms in the
# controlled corpus. Kept deliberately small and explicit.
_ORDINARY_WORDS = {
    "fast", "api", "open", "ai", "next", "js", "sql", "alchemy", "tensor",
    "flow", "web", "auth", "python", "rust", "react", "apple", "amazon",
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "is", "are",
    "cube", "control", "tube", "node", "go", "swift", "kotlin",
}


def _norm_alnum(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _tokens(s: str) -> List[str]:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()


def _char_ngrams(s: str, n: int = 2) -> set:
    s = _norm_alnum(s)
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else {s}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Candidate:
    """One technical entity the corrector may propose.

    - ``canonical``: the written form to emit (e.g. "PostgreSQL").
    - ``spoken_variants``: alnum-normalized surface forms the ASR might produce
      for this entity (e.g. "postgresql", "postgres", "postgrey sql"). Matching
      is done against these.
    - ``context_weights``: per-profile multiplier in [0,1+] applied to the base
      score. Developer -> ~1.0; Email/Chat -> lower, protecting prose.
    - ``negative_contexts``: profiles in which this candidate is BLOCKED
      entirely (never proposed).
    - ``protected_ordinary``: if True, the candidate is only allowed to correct a
      span that is NOT a clean ordinary-English phrase (unless strong context).
      Set True for entities whose spoken form is an ordinary phrase (FastAPI,
      OpenAI, Next.js, SQLAlchemy, TensorFlow...).
    """

    canonical: str
    spoken_variants: Tuple[str, ...]
    category: str = "technical"
    context_weights: Dict[str, float] = field(default_factory=dict)
    negative_contexts: Tuple[str, ...] = ()
    protected_ordinary: bool = False

    def norm_variants(self) -> List[str]:
        return [_norm_alnum(v) for v in self.spoken_variants if v]


@dataclass
class ComponentScores:
    edit_similarity: float = 0.0
    token_overlap: float = 0.0
    ngram_overlap: float = 0.0
    prefix_agreement: float = 0.0
    suffix_agreement: float = 0.0
    context_weight: float = 1.0
    base_score: float = 0.0        # similarity blend before context
    final_score: float = 0.0       # base_score * context_weight

    def as_dict(self) -> dict:
        return {
            "edit_similarity": round(self.edit_similarity, 4),
            "token_overlap": round(self.token_overlap, 4),
            "ngram_overlap": round(self.ngram_overlap, 4),
            "prefix_agreement": round(self.prefix_agreement, 4),
            "suffix_agreement": round(self.suffix_agreement, 4),
            "context_weight": round(self.context_weight, 4),
            "base_score": round(self.base_score, 4),
            "final_score": round(self.final_score, 4),
        }


@dataclass
class CorrectionDecision:
    """Explainable outcome for one candidate span."""

    original_span: str
    changed: bool
    replacement: Optional[str] = None
    best_candidate: Optional[str] = None
    best_score: float = 0.0
    second_score: float = 0.0
    margin: float = 0.0
    reason: str = ""
    components: Optional[dict] = None


@dataclass
class CorrectionResult:
    raw: str
    text: str
    decisions: List[CorrectionDecision] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.text != self.raw


class CandidatePack:
    """A small bounded set of candidates. Not a knowledge base."""

    def __init__(self, candidates: List[Candidate]):
        self._candidates = list(candidates)

    def __len__(self):
        return len(self._candidates)

    def active_for_context(self, context: Optional[str]) -> List[Candidate]:
        ctx = (context or "normal").lower()
        return [c for c in self._candidates if ctx not in
                {n.lower() for n in c.negative_contexts}]

    def limited(self, max_count: Optional[int]) -> "CandidatePack":
        if max_count is None or max_count >= len(self._candidates):
            return self
        return CandidatePack(self._candidates[:max_count])


# --- scoring config (defaults; swept in the benchmark) ----------------------

@dataclass(frozen=True)
class CorrectorConfig:
    threshold: float = 0.86            # min final score to correct
    margin: float = 0.10               # min separation best vs 2nd candidate
    use_context: bool = True
    use_margin: bool = True
    use_negative_protection: bool = True
    strong_context_weight: float = 1.0  # weight at/above which protected
                                        # ordinary spans may still be corrected
    max_span_words: int = 3            # longest raw span (in words) to consider


class PostASRContextCorrector:
    def __init__(self, pack: CandidatePack, config: Optional[CorrectorConfig] = None):
        self._pack = pack
        self._cfg = config or CorrectorConfig()

    # --- scoring --------------------------------------------------------
    def _score_variant(self, span_norm: str, span_tokens: List[str],
                       variant: str) -> ComponentScores:
        cs = ComponentScores()
        cs.edit_similarity = SequenceMatcher(None, span_norm, variant).ratio()
        cs.token_overlap = _overlap(set(span_tokens), set(_tokens(variant)))
        cs.ngram_overlap = _overlap(_char_ngrams(span_norm), _char_ngrams(variant))
        cs.prefix_agreement = 1.0 if span_norm[:2] == variant[:2] and span_norm else 0.0
        cs.suffix_agreement = 1.0 if span_norm[-2:] == variant[-2:] and span_norm else 0.0
        # Deterministic blend; weights fixed (no ML). Edit similarity dominates,
        # ngram/token provide robustness, prefix/suffix small tie-breakers.
        cs.base_score = (
            0.60 * cs.edit_similarity
            + 0.20 * cs.ngram_overlap
            + 0.10 * cs.token_overlap
            + 0.05 * cs.prefix_agreement
            + 0.05 * cs.suffix_agreement
        )
        return cs

    def _best_candidate_for_span(self, span: str, context: Optional[str],
                                 candidates: List[Candidate]):
        span_norm = _norm_alnum(span)
        span_tokens = _tokens(span)
        if not span_norm:
            return None
        scored = []  # (final_score, base_score, cand, components)
        for cand in candidates:
            best_cs = None
            for v in cand.norm_variants():
                cs = self._score_variant(span_norm, span_tokens, v)
                if best_cs is None or cs.base_score > best_cs.base_score:
                    best_cs = cs
            if best_cs is None:
                continue
            # Context weight.
            if self._cfg.use_context:
                ctx = (context or "normal").lower()
                best_cs.context_weight = cand.context_weights.get(ctx, 1.0)
            else:
                best_cs.context_weight = 1.0
            best_cs.final_score = best_cs.base_score * best_cs.context_weight
            scored.append((best_cs.final_score, cand, best_cs))
        if not scored:
            return None
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored

    def _span_is_ordinary_phrase(self, span: str) -> bool:
        """True if every word of the span is an ordinary-English guard word
        (i.e. the ASR produced a clean ordinary phrase, not a mangled token)."""
        toks = _tokens(span)
        return bool(toks) and all(t in _ORDINARY_WORDS for t in toks)

    def _decide_span(self, span: str, context: Optional[str],
                     candidates: List[Candidate]) -> CorrectionDecision:
        scored = self._best_candidate_for_span(span, context, candidates)
        if not scored:
            return CorrectionDecision(span, changed=False, reason="no_candidate")
        best_score, best_cand, best_cs = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score

        dec = CorrectionDecision(
            original_span=span, changed=False,
            best_candidate=best_cand.canonical, best_score=round(best_score, 4),
            second_score=round(second_score, 4), margin=round(margin, 4),
            components=best_cs.as_dict(),
        )

        # Gate 1: threshold.
        if best_score < self._cfg.threshold:
            dec.reason = "below_threshold"
            return dec
        # Gate 2: margin.
        if self._cfg.use_margin and margin < self._cfg.margin:
            dec.reason = "insufficient_margin"
            return dec
        # Gate 3: ordinary-language protection. If the span is a clean ordinary
        # phrase AND the candidate is protected_ordinary, only correct under
        # strong context (weight >= strong_context_weight). Otherwise leave it.
        if (self._cfg.use_negative_protection and best_cand.protected_ordinary
                and self._span_is_ordinary_phrase(span)):
            if best_cs.context_weight < self._cfg.strong_context_weight:
                dec.reason = "ordinary_language_protected"
                return dec
        # Gate 4: identical form (already canonical, nothing to do).
        if span == best_cand.canonical:
            dec.reason = "already_canonical"
            return dec

        dec.changed = True
        dec.replacement = best_cand.canonical
        dec.reason = "corrected"
        return dec

    # --- public API -----------------------------------------------------
    def correct(self, text: str, context: Optional[str] = None,
                max_candidates: Optional[int] = None) -> CorrectionResult:
        """Return a CorrectionResult. Fail-safe: on any error returns the input
        unchanged. Deterministic for a given (text, context, pack, config)."""
        result = CorrectionResult(raw=text or "", text=text or "")
        if not text or not text.strip() or len(self._pack) == 0:
            return result
        try:
            candidates = self._pack.limited(max_candidates).active_for_context(context)
            if not candidates:
                return result

            words = text.split()
            n = len(words)
            # Scan spans of 1..max_span_words. Greedy left-to-right; a corrected
            # span consumes its words so there is no overlap/re-trigger (single
            # bounded pass => deterministic, no loops).
            out_words: List[str] = []
            i = 0
            max_w = self._cfg.max_span_words
            while i < n:
                best_dec = None
                best_len = 0
                for span_len in range(min(max_w, n - i), 0, -1):
                    span = " ".join(words[i:i + span_len])
                    dec = self._decide_span(span, context, candidates)
                    if dec.changed:
                        # Prefer the LONGEST changed span (phrase over token).
                        best_dec = dec
                        best_len = span_len
                        break
                if best_dec is not None:
                    out_words.append(best_dec.replacement)
                    result.decisions.append(best_dec)
                    i += best_len
                else:
                    out_words.append(words[i])
                    i += 1
            result.text = " ".join(out_words)
            return result
        except Exception:
            # Fail-safe: never raise into a caller; return input unchanged.
            return CorrectionResult(raw=text, text=text)
