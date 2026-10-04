"""Phase 9C deterministic candidate retrieval.

Given a raw transcript span + 8A context, retrieve a SMALL ranked list of
relevant KnowledgeTerms from the local index. This answers "what could this word
be?" — it does NOT decide whether to change anything (that stays in the proven
9B corrector). Deterministic, local, no embeddings, no network.

Retrieval signals (bounded, deterministic): exact normalized match, char-ngram
overlap, token overlap, prefix agreement, edit similarity, plus a per-context
domain prior and a source/relevance prior. 6J user terms are given priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from .index import KnowledgeIndex, _char_ngrams
from .models import KnowledgeTerm, Domain, normalize_compact, normalize_text


@dataclass
class RetrievedCandidate:
    term: KnowledgeTerm
    score: float
    matched_form: str
    components: Dict[str, float]


# Per-context domain priors: how much each context favors each domain. Context
# REDUCES candidate space / reweights it — it never fabricates substitutions
# (the 9B corrector still gates every change). Email/Chat down-weight developer
# knowledge so ordinary prose is not flooded with technical candidates.
_CONTEXT_DOMAIN_PRIOR: Dict[str, Dict[str, float]] = {
    "developer": {Domain.DEVELOPER: 1.0, Domain.DATA_SCIENCE: 0.9, Domain.DEVOPS: 0.9,
                  Domain.AI_ML: 0.9, Domain.SECURITY: 0.9, Domain.GENERAL: 0.5},
    "prompt": {Domain.DEVELOPER: 1.0, Domain.AI_ML: 1.0, Domain.GENERAL: 0.6},
    "notes": {Domain.DEVELOPER: 0.7, Domain.GENERAL: 0.7},
    "normal": {Domain.DEVELOPER: 0.7, Domain.GENERAL: 0.7},
    "email": {Domain.DEVELOPER: 0.35, Domain.GENERAL: 0.8},
    "chat": {Domain.DEVELOPER: 0.4, Domain.GENERAL: 0.8},
}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class CandidateRetriever:
    def __init__(self, index: Optional[KnowledgeIndex],
                 user_terms: Optional[List[KnowledgeTerm]] = None,
                 fallback_terms: Optional[List[KnowledgeTerm]] = None,
                 activation=None,
                 domain_terms: Optional[List[KnowledgeTerm]] = None):
        """``index`` is the main knowledge index (may be None/empty -> fallback).
        ``user_terms`` are 6J-derived terms (highest priority). ``fallback_terms``
        are a small curated set used when the index is missing/corrupt.
        ``domain_terms`` are active-domain pack terms made searchable WITHOUT any
        user-priority boost (they go through the normal ranking gates).
        ``activation`` is an optional DomainActivation; when set, each candidate
        gets a bounded ``domain_relevance`` component the ranker can use as a
        prior (never an override)."""
        self._index = index
        self._user_terms = [t for t in (user_terms or []) if t.is_valid()]
        self._fallback = [t for t in (fallback_terms or []) if t.is_valid()]
        self._domain_terms = [t for t in (domain_terms or []) if t.is_valid()]
        self._activation = activation
        # A tiny index over user+fallback terms so they are always searchable.
        self._aux = KnowledgeIndex(self._user_terms + self._fallback) if (
            self._user_terms or self._fallback) else None
        # A separate index over active-domain terms (no user boost).
        self._domain_idx = KnowledgeIndex(self._domain_terms) if self._domain_terms else None

    def _context_prior(self, context: Optional[str], term: KnowledgeTerm) -> float:
        ctx = (context or "normal").lower()
        prior = _CONTEXT_DOMAIN_PRIOR.get(ctx, _CONTEXT_DOMAIN_PRIOR["normal"])
        return prior.get(term.domain, prior.get(Domain.GENERAL, 0.6))

    def _score_term(self, span_n: str, span_compact: str, span_tokens: set,
                    span_grams: set, term: KnowledgeTerm, context: Optional[str],
                    user_boost: float) -> RetrievedCandidate:
        best = None
        for form in term.all_surface_forms():
            form_compact = normalize_compact(form)
            edit = SequenceMatcher(None, span_compact, form_compact).ratio()
            ngram = _overlap(span_grams, _char_ngrams(form))
            token = _overlap(span_tokens, set(form.split()))
            prefix = 1.0 if span_compact[:2] == form_compact[:2] and span_compact else 0.0
            base = 0.55 * edit + 0.25 * ngram + 0.15 * token + 0.05 * prefix
            if best is None or base > best[0]:
                best = (base, form, {"edit": edit, "ngram": ngram,
                                     "token": token, "prefix": prefix})
        if best is None:
            best = (0.0, term.canonical, {})
        base, matched_form, comp = best
        ctx_prior = self._context_prior(context, term)
        final = base * (0.6 + 0.4 * ctx_prior) * (0.7 + 0.3 * term.relevance) + user_boost
        comp = dict(comp)
        comp["context_prior"] = round(ctx_prior, 3)
        comp["relevance"] = term.relevance
        comp["user_boost"] = user_boost
        if self._activation is not None:
            comp["domain_relevance"] = round(
                self._activation.domain_relevance(term.domain, context), 3)
        return RetrievedCandidate(term=term, score=round(final, 5),
                                  matched_form=matched_form, components=comp)

    def retrieve(self, span: str, context: Optional[str] = None,
                 top_k: int = 5, max_pool: int = 200) -> List[RetrievedCandidate]:
        """Return up to ``top_k`` ranked candidates for ``span``. Deterministic.
        Fail-safe: returns [] on any error (never raises)."""
        try:
            span_n = normalize_text(span)
            if not span_n:
                return []
            span_compact = normalize_compact(span)
            span_tokens = set(span_n.split())
            span_grams = _char_ngrams(span_n)

            scored: Dict[str, RetrievedCandidate] = {}

            def consider(idx: Optional[KnowledgeIndex], user_boost: float):
                if idx is None:
                    return
                for tid in idx.candidate_ids(span, max_pool=max_pool):
                    term = idx.term(tid)
                    cand = self._score_term(span_n, span_compact, span_tokens,
                                            span_grams, term, context, user_boost)
                    key = term.canonical
                    if key not in scored or cand.score > scored[key].score:
                        scored[key] = cand

            # 6J + fallback first (user priority), then main index, then active
            # domain terms (no boost — they pass through the normal ranker gates).
            consider(self._aux, user_boost=0.15)
            consider(self._index, user_boost=0.0)
            consider(self._domain_idx, user_boost=0.0)

            ranked = sorted(scored.values(),
                            key=lambda c: (-c.score, c.term.canonical))
            return ranked[:top_k]
        except Exception:
            return []
