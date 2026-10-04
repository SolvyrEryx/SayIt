"""Phase 9J/9K — single safe entry point for the post-ASR intelligence stack.

Wraps the smallest proven subset (9C retrieval + 9D domain/canonical knowledge
+ 9F ranking/abstention + 9B correction) behind ONE pure method:

    IntelligencePipeline.process(raw_text, context) -> PipelineResult

Design guarantees for safe wiring:
- **Pure post-text.** It receives the raw ASR transcript and a context profile
  string only. It never touches audio, the recorder, the model, the decoder,
  Safe Zones, cancellation, or the clipboard.
- **Fail-safe.** ANY error (missing/corrupt index, ranker/corrector exception)
  returns the input text unchanged. It never raises into the caller.
- **Lazy + cached.** The knowledge index is loaded once on first use.
- **No transcript logging.** Ephemeral per-call diagnostics (decision counts,
  not transcript text) are available via ``last_diagnostics`` for debugging only
  and are never written to disk.
- **Disabled by default.** The pipeline is only invoked when the caller's
  feature flag is on (the pipeline itself does not read settings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .candidate_ranker import CandidateRanker, RankerConfig
from .post_context import CorrectorConfig
from ..knowledge import CandidateRetriever, KnowledgeIndex
from ..knowledge.ranked_adapter import RankedRetrievalAdapter
from ..knowledge.models import KnowledgeTerm
from ..knowledge.personalization import personalized_terms

# Default knowledge index. Prefer the packaged copy under the knowledge package
# (ships with the app; packaging-safe), falling back to the dev artifacts path.
# If neither exists, the pipeline is a no-op (fail-safe), so production never
# breaks on a missing index.
_PACKAGED_INDEX = (
    Path(__file__).resolve().parent.parent / "knowledge" / "data" / "knowledge_index.json"
)
_ARTIFACTS_INDEX = (
    Path(__file__).resolve().parents[4]
    / "artifacts" / "phase9e" / "knowledge_index_entity.json"
)


def _default_index_path() -> Path:
    if _PACKAGED_INDEX.exists():
        return _PACKAGED_INDEX
    return _ARTIFACTS_INDEX

# Evidence-supported operating point revalidated in 9I (0.90–0.92 equivalent).
DEFAULT_THRESHOLD = 0.90


@dataclass
class PipelineResult:
    text: str
    changed: bool = False
    reason: str = ""


class IntelligencePipeline:
    def __init__(self, index_path: Optional[Path] = None,
                 threshold: float = DEFAULT_THRESHOLD,
                 user_vocabulary: Optional[List[dict]] = None,
                 enabled_domains: Optional[List[str]] = None,
                 disabled_domains: Optional[List[str]] = None,
                 domain_aware: bool = False):
        self._index_path = Path(index_path) if index_path else _default_index_path()
        self._threshold = threshold
        self._user_vocab = user_vocabulary
        self._enabled_domains = enabled_domains
        self._disabled_domains = disabled_domains
        self._domain_aware = domain_aware
        self._adapter: Optional[RankedRetrievalAdapter] = None
        self._loaded = False
        self._load_error: Optional[str] = None
        self.last_diagnostics: dict = {}

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._adapter is not None
        self._loaded = True
        try:
            if not self._index_path.exists():
                self._load_error = "index_missing"
                return False
            index = KnowledgeIndex.load(self._index_path)
            user_terms: List[KnowledgeTerm] = (
                personalized_terms(self._user_vocab) if self._user_vocab else [])
            activation = None
            domain_terms: List[KnowledgeTerm] = []
            if self._domain_aware:
                from ..knowledge.domain_activation import DomainActivation, active_terms
                activation = DomainActivation.from_settings(
                    self._enabled_domains, self._disabled_domains)
                # Build the active-domain term set (core + active domain/science
                # packs). These are made searchable alongside the packaged index
                # so domain coverage actually reaches retrieval. Context is left
                # as None here so EXPLICITLY enabled domains are always available;
                # per-span context still drives the ranker's context prior.
                try:
                    domain_terms = active_terms(activation, None)
                except Exception:
                    domain_terms = []
            retriever = CandidateRetriever(index, user_terms=user_terms,
                                           domain_terms=domain_terms,
                                           activation=activation)
            ranker = CandidateRanker(RankerConfig(
                accept_threshold=self._threshold, use_domain=self._domain_aware))
            self._adapter = RankedRetrievalAdapter(
                retriever, ranker, CorrectorConfig(), top_k=10)
            return True
        except Exception as e:  # fail-safe
            self._load_error = f"load_error:{type(e).__name__}"
            self._adapter = None
            return False

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    def process(self, raw_text: str, context: Optional[str] = None) -> PipelineResult:
        """Apply the post-ASR intelligence stack. Fail-safe: returns the input
        unchanged on any error or when the index is unavailable."""
        if not raw_text or not raw_text.strip():
            return PipelineResult(text=raw_text or "", changed=False, reason="empty")
        if not self._ensure_loaded() or self._adapter is None:
            self.last_diagnostics = {"applied": False, "reason": self._load_error or "unavailable"}
            return PipelineResult(text=raw_text, changed=False, reason=self._load_error or "unavailable")
        try:
            result = self._adapter.correct(raw_text, context)
            decisions = self._adapter.last_decisions
            # Ephemeral diagnostics ONLY: counts + decision states, never the
            # transcript text or candidate strings beyond canonical winners.
            self.last_diagnostics = {
                "applied": True,
                "changed": result.changed,
                "num_decisions": len(decisions),
                "num_corrections": sum(1 for d in decisions if d.get("decision") == "correct"),
            }
            return PipelineResult(text=result.text, changed=result.changed,
                                  reason="corrected" if result.changed else "unchanged")
        except Exception as e:  # fail-safe
            self.last_diagnostics = {"applied": False, "reason": f"error:{type(e).__name__}"}
            return PipelineResult(text=raw_text, changed=False, reason=f"error:{type(e).__name__}")
