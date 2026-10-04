"""Phase 9C adapter — retrieval -> 9B post-ASR corrector.

Bridges the local knowledge retriever (Phase 9C) to the proven Phase 9B
corrector WITHOUT modifying the corrector. For an utterance it:

  1. scans candidate spans (1..max_span_words),
  2. retrieves top-K KnowledgeTerms per span from the local index,
  3. converts the union of retrieved terms into 9B Candidate objects
     (deriving context weights + protected_ordinary from the KnowledgeTerm),
  4. runs the UNCHANGED PostASRContextCorrector with that per-utterance pack.

The 9B corrector remains solely responsible for scoring, threshold, margin,
ordinary-language protection, and the final change/no-change decision.

Fail-safe: if retrieval yields nothing, the corrector runs with an empty pack
(returns the transcript unchanged) — never raises.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .models import Domain, KnowledgeTerm
from .retrieval import CandidateRetriever
from ..asr.post_context import (
    Candidate, CandidatePack, CorrectorConfig, PostASRContextCorrector,
)

# Ordinary-English guard words: a KnowledgeTerm whose spoken form is a clean
# ordinary phrase should be protected_ordinary in 9B (only corrected under
# strong context). Reuse the same discipline as the 9B pack.
_ORDINARY = {
    "fast", "api", "open", "ai", "next", "js", "sql", "alchemy", "tensor",
    "flow", "web", "auth", "python", "rust", "react", "go", "swift", "kotlin",
    "node", "vue", "express", "d",
}

# Context weight per domain under each 8A profile (mirrors retrieval priors but
# expressed as the 9B context_weight the corrector multiplies in). >=1.0 lets a
# protected-ordinary span be corrected under strong context.
_DOMAIN_CTX_WEIGHT: Dict[str, Dict[str, float]] = {
    "developer": {"*": 1.0},
    "prompt": {"*": 1.0},
    "notes": {"*": 0.8},
    "normal": {"*": 0.85},
    "email": {"*": 0.5},
    "chat": {"*": 0.55},
}


def _is_ordinary_phrase(forms) -> bool:
    for f in forms:
        toks = f.split()
        if toks and all(t in _ORDINARY for t in toks):
            return True
    return False


def _context_weights_for(term: KnowledgeTerm) -> Dict[str, float]:
    out = {}
    for ctx, m in _DOMAIN_CTX_WEIGHT.items():
        out[ctx] = m.get(term.domain, m.get("*", 1.0))
    return out


def knowledge_term_to_candidate(term: KnowledgeTerm) -> Candidate:
    forms = term.all_surface_forms()
    protected = _is_ordinary_phrase(forms)
    return Candidate(
        canonical=term.canonical,
        spoken_variants=tuple(forms),
        category=term.category,
        context_weights=_context_weights_for(term),
        protected_ordinary=protected,
    )


class RetrievalCorrectionAdapter:
    def __init__(self, retriever: CandidateRetriever,
                 config: Optional[CorrectorConfig] = None,
                 top_k: int = 10):
        self._retriever = retriever
        self._cfg = config or CorrectorConfig()
        self._top_k = top_k

    def _build_pack(self, text: str, context: Optional[str]) -> CandidatePack:
        words = (text or "").split()
        n = len(words)
        seen: Dict[str, Candidate] = {}
        max_w = self._cfg.max_span_words
        for i in range(n):
            for span_len in range(1, min(max_w, n - i) + 1):
                span = " ".join(words[i:i + span_len])
                for rc in self._retriever.retrieve(span, context, top_k=self._top_k):
                    if rc.term.canonical not in seen:
                        seen[rc.term.canonical] = knowledge_term_to_candidate(rc.term)
        return CandidatePack(list(seen.values()))

    def correct(self, text: str, context: Optional[str] = None):
        """Retrieve candidates for the utterance, then run the unchanged 9B
        corrector. Returns the 9B CorrectionResult. Fail-safe."""
        try:
            pack = self._build_pack(text, context)
            corrector = PostASRContextCorrector(pack, self._cfg)
            return corrector.correct(text, context)
        except Exception:
            from ..asr.post_context import CorrectionResult
            return CorrectionResult(raw=text or "", text=text or "")
