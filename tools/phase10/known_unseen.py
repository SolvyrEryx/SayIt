"""Phase 10C — known/unseen term classification + leakage detection.

Classifies each target term as KNOWN (present somewhere in the current SayIt
knowledge system) or UNSEEN. It is READ-ONLY: it never adds terms to the
knowledge base (that would be evaluation leakage).

Knowledge sources consulted (the current production/experimental stack):
  - the packaged knowledge index (9C curated/linguist/npm/pypi + 9D domain
    canonicals + 9E entities), via all surface forms + canonicals
  - the 9D domain canonical_map
  - the 9E entity packs
  - (optionally) a user's explicit 6J vocabulary passed in

A term is KNOWN if its normalized form matches any canonical or spoken variant
in those sources. The central scientific metric is the UNSEEN fraction — only
UNSEEN terms test generalization.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sayit.core.knowledge import KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.models import normalize_text  # noqa: E402
from sayit.core.knowledge.domain_packs import canonical_map  # noqa: E402
from sayit.core.knowledge.entities import entity_terms  # noqa: E402

_PACKAGED_INDEX = ROOT / "src" / "sayit" / "core" / "knowledge" / "data" / "knowledge_index.json"


def build_known_set(user_vocabulary: Optional[List[dict]] = None) -> Set[str]:
    """Collect every normalized surface form the SayIt knowledge system knows.
    READ-ONLY (does not mutate any source)."""
    known: Set[str] = set()

    # Packaged knowledge index (surface forms of every term).
    if _PACKAGED_INDEX.exists():
        idx = KnowledgeIndex.load(_PACKAGED_INDEX)
        for tid in range(idx.term_count):
            t = idx.term(tid)
            for form in t.all_surface_forms():
                known.add(form)
            known.add(normalize_text(t.canonical))

    # 9D canonical map (spoken + canonical forms).
    for k, v in canonical_map().items():
        known.add(normalize_text(k))
        known.add(normalize_text(v))

    # 9E entities.
    for t in entity_terms():
        for form in t.all_surface_forms():
            known.add(form)
        known.add(normalize_text(t.canonical))

    # Explicit 6J user vocabulary (if provided).
    for item in (user_vocabulary or []):
        for key in ("spoken", "written"):
            val = item.get(key)
            if val:
                known.add(normalize_text(val))

    known.discard("")
    return known


def classify_terms(target_terms: List[str], known: Set[str]) -> Dict[str, str]:
    """Return {term: 'KNOWN'|'UNSEEN'} using normalized matching. READ-ONLY."""
    out = {}
    for term in target_terms:
        out[term] = "KNOWN" if normalize_text(term) in known else "UNSEEN"
    return out


def summarize(entries_terms: List[List[str]], known: Set[str]) -> Dict:
    total = 0
    known_count = 0
    per_term = {}
    for terms in entries_terms:
        cls = classify_terms(terms, known)
        for t, c in cls.items():
            total += 1
            if c == "KNOWN":
                known_count += 1
            per_term[t] = c
    return {
        "total_terms": total,
        "known": known_count,
        "unseen": total - known_count,
        "known_fraction": round(known_count / total, 4) if total else None,
        "unseen_fraction": round((total - known_count) / total, 4) if total else None,
        "per_term": per_term,
    }
