"""Phase 9F — deterministic contextual candidate ranking + false-positive control.

Sits between Phase 9C retrieval and Phase 9B correction. Given the retrieved
candidates for an observed ASR span, it decides which candidate (if any) is
trustworthy enough to correct to — producing an explicit decision:

    CORRECT          -> a single trusted winner
    LEAVE_UNCHANGED  -> best candidate too weak / looks ordinary
    AMBIGUOUS        -> two candidates too close to separate safely
    NO_CANDIDATE     -> nothing retrieved

Motivation (measured in 9C): a large knowledge source raises recall but adds
noise (short language names tie/outrank the right term), lowering exact-entity
accuracy and risking false substitutions. The ranker adds the signals 9C/9B
lacked — **source confidence**, **ambiguity penalty**, and **explicit
abstention** on insufficient evidence — so breadth no longer costs precision.

Pure, deterministic, explainable, fail-safe. No GUI coupling, no network, no
LLM, no embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Dict, List, Optional

# Decision states.
class Decision(str, Enum):
    CORRECT = "correct"
    LEAVE_UNCHANGED = "leave_unchanged"
    AMBIGUOUS = "ambiguous"
    NO_CANDIDATE = "no_candidate"


# Source confidence prior: curated/user knowledge is more trustworthy than a
# giant auto-ingested language/package list. A combined source (e.g.
# "curated+linguist") takes the max of its parts.
_SOURCE_CONFIDENCE = {
    "6j": 1.0,
    "user": 1.0,
    "curated": 0.9,
    "npm": 0.6,
    "pypi": 0.6,
    "linguist": 0.5,
}

# Ordinary-English guard: if the observed span is a clean ordinary phrase, a
# protected candidate needs strong context to win (mirrors 9B's protection).
_ORDINARY_WORDS = {
    "fast", "api", "open", "ai", "next", "js", "sql", "alchemy", "tensor",
    "flow", "web", "auth", "python", "rust", "react", "go", "swift", "node",
    "java", "ruby", "scala", "kotlin", "spark", "flask", "express", "helm",
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "is",
    "cube", "control", "tube", "flow", "apple", "amazon", "jordan",
    "model", "plant", "state", "gain", "phase", "root", "mach",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def _compact(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def source_confidence(source: str) -> float:
    if not source:
        return 0.5
    parts = re.split(r"[+/]", source.lower())
    return max((_SOURCE_CONFIDENCE.get(p.strip(), 0.5) for p in parts), default=0.5)


@dataclass
class RankerConfig:
    accept_threshold: float = 0.72   # min final score to CORRECT
    margin: float = 0.08             # min separation winner vs runner-up
    ambiguity_band: float = 0.04     # within this -> AMBIGUOUS, not just weak
    strong_context: float = 0.9      # context_relevance >= this allows ordinary override
    # feature weights (transparent; swept/ablated in the benchmark)
    w_retrieval: float = 0.45
    w_context: float = 0.20
    w_source: float = 0.20
    w_phrase: float = 0.15
    w_domain: float = 0.10          # bounded domain-relevance PRIOR (never an override)
    use_context: bool = True
    use_source_confidence: bool = True
    use_ambiguity: bool = True
    use_ordinary_penalty: bool = True
    use_abstention: bool = True
    use_domain: bool = False        # off by default -> ARM B is byte-identical


@dataclass
class RankedCandidate:
    canonical: str
    score: float
    components: Dict[str, float]
    source: str


@dataclass
class RankedDecision:
    decision: Decision
    winner: Optional[str] = None          # canonical form to correct to
    score: float = 0.0
    runner_up: Optional[str] = None
    margin: float = 0.0
    reason: str = ""
    ranked: List[RankedCandidate] = field(default_factory=list)

    @property
    def should_correct(self) -> bool:
        return self.decision is Decision.CORRECT


class CandidateRanker:
    def __init__(self, config: Optional[RankerConfig] = None):
        self._cfg = config or RankerConfig()

    # --- per-candidate scoring -----------------------------------------
    def _retrieval_similarity(self, span: str, cand) -> float:
        """Max edit similarity of the span against the candidate's surface forms.
        Works with a RetrievedCandidate (has .term.all_surface_forms) or a plain
        object exposing .matched_form."""
        span_c = _compact(span)
        forms = []
        term = getattr(cand, "term", None)
        if term is not None and hasattr(term, "all_surface_forms"):
            forms = term.all_surface_forms()
        mf = getattr(cand, "matched_form", None)
        if mf:
            forms = forms or [mf]
        if not forms:
            return 0.0
        return max(SequenceMatcher(None, span_c, _compact(f)).ratio() for f in forms)

    def _context_relevance(self, cand) -> float:
        comp = getattr(cand, "components", {}) or {}
        # 9C already computed a context_prior per candidate.
        return float(comp.get("context_prior", 0.6))

    def _phrase_strength(self, span: str, cand) -> float:
        """Multi-word candidates matched as whole phrases are stronger signals
        than single short tokens (which collide more)."""
        canon = getattr(getattr(cand, "term", None), "canonical", "") or ""
        words = len(_norm(canon).split())
        # Longer canonical phrases get higher strength; very short (<=3 char)
        # single tokens get a penalty (collision-prone).
        if words >= 2:
            return 1.0
        return 0.75 if len(_compact(canon)) >= 4 else 0.4

    def _candidate_score(self, span: str, cand) -> RankedCandidate:
        cfg = self._cfg
        term = getattr(cand, "term", None)
        canon = getattr(term, "canonical", "") or getattr(cand, "canonical", "")
        src = getattr(term, "source", "") or "curated"

        retr = self._retrieval_similarity(span, cand)
        ctx = self._context_relevance(cand) if cfg.use_context else 1.0
        srcc = source_confidence(src) if cfg.use_source_confidence else 1.0
        phrase = self._phrase_strength(span, cand)

        base = (cfg.w_retrieval * retr + cfg.w_context * ctx
                + cfg.w_source * srcc + cfg.w_phrase * phrase)

        # Ordinary-word penalty: if the span is a clean ordinary phrase, down-
        # weight unless context is strong (protect ordinary language).
        toks = _norm(span).split()
        is_ordinary_span = bool(toks) and all(t in _ORDINARY_WORDS for t in toks)
        ordinary_pen = 0.0
        if cfg.use_ordinary_penalty and is_ordinary_span:
            # Multi-word ordinary spans can be rescued by strong context; a LONE
            # ordinary-collision token (java, go, rust, control) stays protected
            # even in developer context — context is not evidence that a bare
            # ordinary word is the technical entity.
            single_token = len(toks) == 1
            if single_token or ctx < cfg.strong_context:
                ordinary_pen = 0.25
        # Ambiguity-class penalty (9E): entities flagged ordinary/proper collide
        # with ordinary words or proper names, so require stronger evidence.
        meta = getattr(term, "metadata", {}) or {}
        amb = meta.get("ambiguity_class", "none")
        is_ambiguous = amb in ("ordinary", "proper")
        ambiguity_pen = 0.0
        if cfg.use_ambiguity and is_ambiguous and ctx < cfg.strong_context:
            ambiguity_pen = 0.20 if amb == "ordinary" else 0.15

        # Bounded domain-relevance PRIOR (opt-in). It is one additive feature
        # among many, clamped to [0,1]. CRITICAL SAFETY RULE: a domain being
        # active is NOT strong evidence for an ambiguous (ordinary/proper) entity
        # or a clean ordinary span. The prior is therefore SUPPRESSED in those
        # cases unless context is strong — so "developer domain active" can never
        # turn ordinary "rust"/"go"/"swift" into the technical entity. The prior
        # only helps unambiguous technical candidates.
        dom_rel = 0.0
        dom_contrib = 0.0
        if cfg.use_domain:
            comp_in = getattr(cand, "components", {}) or {}
            dom_rel = max(0.0, min(1.0, float(comp_in.get("domain_relevance", 0.6))))
            # The domain prior helps candidates that carry their own technical
            # signal and are collision-free: MULTI-WORD phrases (e.g. "Reynolds
            # number", "Bode plot") and ALL-CAPS ACRONYMS (e.g. HPLC, LQR, FFT).
            # It is still SUPPRESSED for ambiguity-flagged (ordinary/proper)
            # candidates and bare ordinary tokens, so domain activity never turns
            # ordinary "java"/"go"/"control" into an entity.
            canon_words = len(_norm(canon).split())
            is_multiword = canon_words >= 2
            canon_bare = canon.replace(".", "").replace("-", "")
            is_acronym = (len(canon_bare) >= 2 and canon_bare.isupper())
            is_technical_shape = is_multiword or is_acronym
            suppress = is_ambiguous or (is_ordinary_span and ctx < cfg.strong_context) \
                or not is_technical_shape
            if not suppress:
                dom_contrib = cfg.w_domain * dom_rel
                base = base + dom_contrib

        final = max(0.0, base - ordinary_pen - ambiguity_pen)
        comp = {
            "retrieval_similarity": round(retr, 4),
            "context_relevance": round(ctx, 4),
            "source_confidence": round(srcc, 4),
            "phrase_strength": round(phrase, 4),
            "domain_relevance": round(dom_rel, 4),
            "domain_contribution": round(dom_contrib, 4),
            "ordinary_penalty": round(ordinary_pen, 4),
            "ambiguity_penalty": round(ambiguity_pen, 4),
            "ambiguity_class": amb,
            "base": round(base, 4),
        }
        return RankedCandidate(canonical=canon, score=round(final, 5),
                               components=comp, source=src)

    # --- public API -----------------------------------------------------
    def rank(self, observed_span: str, candidates, context: Optional[str] = None,
             domain: Optional[str] = None, metadata: Optional[dict] = None) -> RankedDecision:
        """Rank candidates and decide. Pure/deterministic/fail-safe."""
        try:
            cfg = self._cfg
            cands = list(candidates or [])
            if not cands:
                return RankedDecision(Decision.NO_CANDIDATE, reason="no candidates retrieved")

            ranked = [self._candidate_score(observed_span, c) for c in cands]
            # Deterministic order: score desc, then canonical asc.
            ranked.sort(key=lambda r: (-r.score, r.canonical))
            winner = ranked[0]
            runner = ranked[1] if len(ranked) > 1 else None
            margin = winner.score - (runner.score if runner else 0.0)

            dec = RankedDecision(
                decision=Decision.LEAVE_UNCHANGED, winner=None,
                score=winner.score, runner_up=runner.canonical if runner else None,
                margin=round(margin, 5), ranked=ranked,
            )

            if not cfg.use_abstention:
                dec.decision = Decision.CORRECT
                dec.winner = winner.canonical
                dec.reason = "abstention disabled"
                return dec

            # Gate 1: absolute threshold.
            if winner.score < cfg.accept_threshold:
                dec.reason = f"winner score {winner.score:.3f} < threshold {cfg.accept_threshold}"
                return dec
            # Gate 2: ambiguity — two candidates too close.
            if cfg.use_ambiguity and runner is not None and margin < cfg.ambiguity_band:
                dec.decision = Decision.AMBIGUOUS
                dec.reason = (f"top two within ambiguity band "
                              f"({winner.canonical} vs {runner.canonical}, margin {margin:.3f})")
                return dec
            # Gate 3: margin.
            if runner is not None and margin < cfg.margin:
                dec.reason = f"insufficient margin {margin:.3f} < {cfg.margin}"
                return dec

            dec.decision = Decision.CORRECT
            dec.winner = winner.canonical
            dec.reason = (f"accepted: score {winner.score:.3f} >= {cfg.accept_threshold}, "
                          f"margin {margin:.3f}, source {winner.source}")
            return dec
        except Exception as e:  # fail-safe: never raise into caller
            return RankedDecision(Decision.LEAVE_UNCHANGED, reason=f"ranker error (safe): {e}")
