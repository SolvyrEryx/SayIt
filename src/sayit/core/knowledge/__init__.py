"""Phase 9C — local knowledge + contextual candidate retrieval.

A local-first layer that automatically produces a SMALL set of relevant
technical candidates for the proven Phase 9B post-ASR corrector. The central
rule is:

    LARGE DATASET -> LOCAL INDEX -> RELEVANT LOOKUP -> SMALL CANDIDATE SET

never "load everything and feed everything to the corrector". No network at
runtime, no embeddings, no API keys. Everything here is deterministic and
operates on a compact local index built from curated/ingested data.
"""

from .models import KnowledgeTerm, Domain
from .index import KnowledgeIndex
from .retrieval import CandidateRetriever, RetrievedCandidate
from .domain_activation import (
    DomainActivation, DOMAIN_GROUPS, all_domain_names, active_terms,
    build_active_index,
)

__all__ = [
    "KnowledgeTerm",
    "Domain",
    "KnowledgeIndex",
    "CandidateRetriever",
    "RetrievedCandidate",
    "DomainActivation",
    "DOMAIN_GROUPS",
    "all_domain_names",
    "active_terms",
    "build_active_index",
]
