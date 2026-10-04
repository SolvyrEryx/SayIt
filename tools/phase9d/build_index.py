"""Phase 9D — build the domain-enhanced knowledge index.

Merges the 9D domain packs (which carry OFFICIAL canonical casings) with the
9C ingested sources (Linguist + curated npm/PyPI subset). Domain-pack canonicals
WIN on casing (that is the whole point of 9D-B), so e.g. the lowercase npm
"fastapi" is superseded by the official "FastAPI".

Emits:
  artifacts/phase9d/knowledge_index_domain.json  (the merged index)
  artifacts/phase9d/pack_statistics.json
  artifacts/phase9d/canonical_statistics.json
  artifacts/phase9d/DOMAIN_SOURCE_MANIFEST.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.knowledge.index import KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.models import KnowledgeTerm, normalize_text  # noqa: E402
from sayit.core.knowledge.domain_packs import (  # noqa: E402
    CANONICAL_VERSION, DOMAIN_PACKS, PACK_SCHEMA_VERSION, pack_stats, pack_terms,
)

ART = ROOT / "artifacts" / "phase9d"
C9 = ROOT / "artifacts" / "phase9" / "9C" / "ingested"


def _load(path: Path):
    if not path.exists():
        return []
    return [KnowledgeTerm.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def merge(domain_terms, other_groups):
    """Domain packs first (canonical authority). Other sources only add NEW
    canonicals (by normalized canonical key); they never override a domain
    pack's canonical casing. Variants are merged in."""
    by_norm = {}
    order = []

    def add(t, is_domain):
        key = normalize_text(t.canonical)
        if key not in by_norm:
            by_norm[key] = t
            order.append(key)
        else:
            ex = by_norm[key]
            variants = tuple(dict.fromkeys([*ex.spoken_variants, *t.spoken_variants]))
            # Keep the domain-pack canonical if either is a domain term.
            canonical = ex.canonical  # ex came first (domain if domain-first)
            by_norm[key] = KnowledgeTerm(
                canonical=canonical, spoken_variants=variants,
                category=ex.category, domain=ex.domain,
                source=ex.source + "+" + t.source,
                relevance=max(ex.relevance, t.relevance), metadata=ex.metadata)

    for t in domain_terms:
        add(t, True)
    for grp in other_groups:
        for t in grp:
            add(t, False)
    return [by_norm[k] for k in order]


def main():
    ART.mkdir(parents=True, exist_ok=True)
    domain_terms = pack_terms()
    linguist = _load(C9 / "linguist_terms.json")
    pkgs = _load(C9 / "npm_pypi_terms.json")

    terms = merge(domain_terms, [pkgs, linguist])
    index = KnowledgeIndex.from_terms(terms)
    idx_path = ART / "knowledge_index_domain.json"
    index.save(idx_path)

    stats = index.stats()
    stats["index_file_bytes"] = idx_path.stat().st_size
    stats["domain_term_count"] = len(domain_terms)
    stats["merged_total"] = len(terms)
    (ART / "pack_statistics.json").write_text(
        json.dumps({"packs": pack_stats(), "index": stats,
                    "pack_schema_version": PACK_SCHEMA_VERSION}, indent=2), encoding="utf-8")

    # Canonical statistics: how many terms now carry an official canonical form.
    canon = {"total": len(terms),
             "with_official_canonical": sum(
                 1 for t in terms if t.metadata.get("canonical_confidence") == "0.95"),
             "canonical_version": CANONICAL_VERSION}
    (ART / "canonical_statistics.json").write_text(json.dumps(canon, indent=2), encoding="utf-8")

    manifest = f"""# Phase 9D Domain Source Manifest

Build date: {datetime.now(timezone.utc).isoformat()}
Pack schema version: {PACK_SCHEMA_VERSION}
Canonical version: {CANONICAL_VERSION}

## Domain packs (curated, local, inert data)
"""
    for name, terms_d in DOMAIN_PACKS.items():
        manifest += f"- **{name}**: {len(terms_d)} terms (project MIT; canonical forms are official published casings)\n"
    manifest += """
## Upstream sources merged (from Phase 9C, build-time only)
- github-linguist/linguist — languages.yml — MIT — 634 language terms
- nice-registry/all-the-package-names — MIT — curated real subset (full 117MB LFS NOT loaded)
- sethmlarson/pypi-data — Apache-2.0 — curated real subset

## Canonicalization policy
Canonical casing is EVIDENCE-DRIVEN (official project published form), NOT
generic title-casing. Domain-pack canonicals override lowercase package-source
canonicals (e.g. npm 'fastapi' -> official 'FastAPI').

## Runtime
No runtime network. No API keys. Local index only.
"""
    (ART / "DOMAIN_SOURCE_MANIFEST.md").write_text(manifest, encoding="utf-8")

    print(f"domain index: {len(terms)} terms ({len(domain_terms)} domain), "
          f"{stats['index_file_bytes']} bytes; official canonicals="
          f"{canon['with_official_canonical']}")


if __name__ == "__main__":
    main()
