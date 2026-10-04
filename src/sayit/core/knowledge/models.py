"""Phase 9C knowledge schema — normalized term representation.

A ``KnowledgeTerm`` is a single canonical technical entity plus the forms the
ASR might produce for it. It is source-agnostic: Linguist languages, curated
npm/PyPI packages, and 6J user vocabulary all normalize to this shape. It is
plain data (JSON-serializable); it carries no behavior and is never executed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


class Domain:
    GENERAL = "general"
    DEVELOPER = "developer"
    DATA_SCIENCE = "data_science"
    DEVOPS = "devops"
    SECURITY = "security"
    AI_ML = "ai_ml"
    AEROSPACE = "aerospace"
    CONTROL = "control"
    CHEMISTRY = "chemistry"
    ELECTRONICS = "electronics"
    MATHEMATICS = "mathematics"


def normalize_text(s: str) -> str:
    """Lowercase, strip to alnum+spaces, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def normalize_compact(s: str) -> str:
    """Alnum-only lowercase (for edit/ngram matching)."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


@dataclass
class KnowledgeTerm:
    canonical: str                       # written form to emit, e.g. "PostgreSQL"
    spoken_variants: Tuple[str, ...] = ()  # surface forms the ASR may produce
    category: str = "term"               # language/framework/library/package/...
    domain: str = Domain.DEVELOPER
    source: str = "curated"              # linguist / npm / pypi / curated / 6j
    aliases: Tuple[str, ...] = ()
    relevance: float = 0.5               # 0..1 source/importance prior
    enabled: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def normalized(self) -> str:
        return normalize_text(self.canonical)

    def all_surface_forms(self) -> List[str]:
        """Every lowercase surface form used for matching (canonical + variants
        + aliases), de-duplicated, order-stable."""
        forms = [self.canonical, *self.spoken_variants, *self.aliases]
        seen = set()
        out = []
        for f in forms:
            n = normalize_text(f)
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def to_dict(self) -> dict:
        return {
            "canonical": self.canonical,
            "spoken_variants": list(self.spoken_variants),
            "category": self.category,
            "domain": self.domain,
            "source": self.source,
            "aliases": list(self.aliases),
            "relevance": self.relevance,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeTerm":
        return cls(
            canonical=str(d.get("canonical", "")),
            spoken_variants=tuple(d.get("spoken_variants", []) or []),
            category=str(d.get("category", "term")),
            domain=str(d.get("domain", Domain.DEVELOPER)),
            source=str(d.get("source", "curated")),
            aliases=tuple(d.get("aliases", []) or []),
            relevance=float(d.get("relevance", 0.5) or 0.5),
            enabled=bool(d.get("enabled", True)),
            metadata=dict(d.get("metadata", {}) or {}),
        )

    def is_valid(self) -> bool:
        return bool(self.canonical.strip())
