"""Phase 9F — retrieve-once + rank + correct adapter.

Flow (one retrieval per span, unlike the 9C adapter which re-retrieved):

    for each span:
        candidates = retriever.retrieve(span)   # 9C, once
        decision   = ranker.rank(span, candidates, context)  # 9F
        if decision.CORRECT: add winner term to the trusted pack
    corrected = PostASRContextCorrector(trusted_pack).correct(text, context)  # 9B

The 9B corrector remains unchanged and still applies its own threshold/margin/
ordinary-protection gates — the ranker only decides which candidates are
trustworthy enough to even be offered. This both de-noises (fixing the 9C
exact-accuracy loss) and avoids repeated retrieval (latency).

Fail-safe: any error yields the transcript unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import KnowledgeTerm
from .retrieval import CandidateRetriever
from ..asr.candidate_ranker import CandidateRanker, Decision, RankerConfig
from ..asr.post_context import (
    Candidate, CandidatePack, CorrectorConfig, PostASRContextCorrector,
)
from .adapter import knowledge_term_to_candidate


class RankedRetrievalAdapter:
    def __init__(self, retriever: CandidateRetriever,
                 ranker: Optional[CandidateRanker] = None,
                 corrector_config: Optional[CorrectorConfig] = None,
                 ranker_config: Optional[RankerConfig] = None,
                 top_k: int = 10):
        self._retriever = retriever
        self._ranker = ranker or CandidateRanker(ranker_config)
        self._cfg = corrector_config or CorrectorConfig()
        self._top_k = top_k
        self._last_decisions: List[dict] = []

    @property
    def last_decisions(self) -> List[dict]:
        """Explainability: ranker decisions from the most recent correct()."""
        return self._last_decisions

    def _build_trusted_pack(self, text: str, context: Optional[str]):
        words = (text or "").split()
        n = len(words)
        max_w = self._cfg.max_span_words
        trusted: Dict[str, Candidate] = {}
        decisions: List[dict] = []
        # Map canonical -> KnowledgeTerm so an approved winner can be converted.
        for i in range(n):
            for span_len in range(1, min(max_w, n - i) + 1):
                span = " ".join(words[i:i + span_len])
                cands = self._retriever.retrieve(span, context, top_k=self._top_k)
                if not cands:
                    continue
                dec = self._ranker.rank(span, cands, context)
                if dec.decision is Decision.CORRECT and dec.winner:
                    # Find the retrieved term whose canonical matches the winner.
                    for rc in cands:
                        if rc.term.canonical == dec.winner:
                            trusted.setdefault(rc.term.canonical,
                                               knowledge_term_to_candidate(rc.term))
                            break
                decisions.append({
                    "span": span, "decision": dec.decision.value,
                    "winner": dec.winner, "score": dec.score,
                    "margin": dec.margin, "reason": dec.reason,
                })
        self._last_decisions = decisions
        return CandidatePack(list(trusted.values()))

    def correct(self, text: str, context: Optional[str] = None):
        try:
            pack = self._build_trusted_pack(text, context)
            return PostASRContextCorrector(pack, self._cfg).correct(text, context)
        except Exception:
            from ..asr.post_context import CorrectionResult
            return CorrectionResult(raw=text or "", text=text or "")
