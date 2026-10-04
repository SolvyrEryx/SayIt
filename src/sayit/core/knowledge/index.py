"""Phase 9C compact local knowledge index.

Backs fast deterministic lookup over KnowledgeTerms without loading a giant
Python list per query. The index is built once (from ingested/curated terms)
and stored as compact JSON; at load time it builds in-memory postings:

- exact map:   normalized surface form -> term ids (O(1) exact hits)
- token postings: token -> set(term ids)        (multi-word / token overlap)
- char-ngram postings: 3-gram -> set(term ids)  (fuzzy candidate generation
  WITHOUT scanning all terms)

Candidate generation uses the postings to produce a BOUNDED candidate id set
for a query span, so retrieval cost scales with the query, not the corpus. The
JSON index is the single serialized artifact (no SQLite dependency added; a
measurement-justified backend swap is possible later).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

from .models import KnowledgeTerm, normalize_compact, normalize_text

_NGRAM = 3


def _char_ngrams(s: str, n: int = _NGRAM) -> Set[str]:
    s = normalize_compact(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


class KnowledgeIndex:
    def __init__(self, terms: List[KnowledgeTerm]):
        self._terms: List[KnowledgeTerm] = [t for t in terms if t.is_valid() and t.enabled]
        self._exact: Dict[str, List[int]] = defaultdict(list)
        self._token_post: Dict[str, Set[int]] = defaultdict(set)
        self._ngram_post: Dict[str, Set[int]] = defaultdict(set)
        self._build()

    def _build(self) -> None:
        for tid, term in enumerate(self._terms):
            for form in term.all_surface_forms():
                self._exact[form].append(tid)
                for tok in form.split():
                    self._token_post[tok].add(tid)
                for g in _char_ngrams(form):
                    self._ngram_post[g].add(tid)

    # --- stats ----------------------------------------------------------
    @property
    def term_count(self) -> int:
        return len(self._terms)

    def stats(self) -> dict:
        return {
            "term_count": len(self._terms),
            "exact_forms": len(self._exact),
            "token_postings": len(self._token_post),
            "ngram_postings": len(self._ngram_post),
        }

    def term(self, tid: int) -> KnowledgeTerm:
        return self._terms[tid]

    # --- candidate generation (bounded) ---------------------------------
    def candidate_ids(self, span: str, max_pool: int = 200) -> List[int]:
        """Return a BOUNDED set of candidate term ids plausibly matching span.

        Combines exact-form hits, token-posting hits, and char-ngram-posting
        hits. Deterministic ordering (by id). Capped at ``max_pool`` so a query
        never fans out to the whole corpus.
        """
        span_n = normalize_text(span)
        if not span_n:
            return []
        ids: Set[int] = set()
        # 1) exact surface form.
        ids.update(self._exact.get(span_n, []))
        # 2) token postings (any shared token).
        for tok in span_n.split():
            ids.update(self._token_post.get(tok, set()))
        # 3) char-ngram postings (fuzzy; shared 3-grams).
        grams = _char_ngrams(span_n)
        gram_hits: Dict[int, int] = defaultdict(int)
        for g in grams:
            for tid in self._ngram_post.get(g, set()):
                gram_hits[tid] += 1
        # Keep ngram hits with the most shared grams first (bounded).
        for tid, _ in sorted(gram_hits.items(), key=lambda kv: (-kv[1], kv[0])):
            ids.add(tid)
            if len(ids) >= max_pool:
                break
        return sorted(ids)[:max_pool]

    # --- persistence ----------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({"terms": [t.to_dict() for t in self._terms]})

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        terms = [KnowledgeTerm.from_dict(d) for d in data.get("terms", [])]
        return cls(terms)

    @classmethod
    def from_terms(cls, terms: List[KnowledgeTerm]) -> "KnowledgeIndex":
        return cls(terms)
