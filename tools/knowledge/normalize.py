"""Phase 9C build step — normalize + merge sources into the local index.

Merges:
  - Linguist language terms (ingested/linguist_terms.json)
  - curated npm/PyPI package terms (ingested/npm_pypi_terms.json)
  - a small curated technical pack (databases/protocols/tools whose mis-heard
    forms the 9A.2 corpus exercises, e.g. PostgreSQL/WebAuthn/kubectl) — these
    are not languages or packages so are not covered by the above sources.

De-duplicates by normalized canonical form (first source wins, variants merged),
builds the KnowledgeIndex, saves it, and writes provenance artifacts.

Usage:
    uv run python tools/knowledge/normalize.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.knowledge.models import Domain, KnowledgeTerm, normalize_text  # noqa: E402
from sayit.core.knowledge.index import KnowledgeIndex  # noqa: E402

ART = ROOT / "artifacts" / "phase9" / "9C"
INGESTED = ART / "ingested"

# Curated technical entities whose mis-heard forms appear in the corpus and
# which are NOT languages/packages. Spoken variants include the real ASR
# mis-hearings observed in 9A.2 (so retrieval can surface them).
_CURATED_TECH = [
    KnowledgeTerm("PostgreSQL", ("postgresql", "postgres", "post gres sql",
                  "postgrey sql", "post dre sql", "postjsql"), "database",
                  Domain.DEVELOPER, "curated", relevance=0.8),
    KnowledgeTerm("WebAuthn", ("webauthn", "web auth n", "web auth", "webant"),
                  "protocol", Domain.SECURITY, "curated", relevance=0.75),
    KnowledgeTerm("kubectl", ("kubectl", "kube control", "cube control",
                  "tube control", "ubitil", "hubitel"), "tool",
                  Domain.DEVOPS, "curated", relevance=0.75),
    KnowledgeTerm("GitHub", ("github", "git hub"), "platform", Domain.DEVELOPER,
                  "curated", relevance=0.8),
    KnowledgeTerm("Docker", ("docker",), "tool", Domain.DEVOPS, "curated", relevance=0.8),
    KnowledgeTerm("Kubernetes", ("kubernetes", "kube netes"), "tool",
                  Domain.DEVOPS, "curated", relevance=0.75),
    KnowledgeTerm("OpenAI", ("openai", "open ai"), "company", Domain.AI_ML,
                  "curated", relevance=0.7),
    KnowledgeTerm("GitHub Actions", ("github actions", "git hub actions"),
                  "phrase", Domain.DEVOPS, "curated", relevance=0.7),
    KnowledgeTerm("Docker Compose", ("docker compose",), "phrase",
                  Domain.DEVOPS, "curated", relevance=0.7),
    KnowledgeTerm("vector database", ("vector database",), "phrase",
                  Domain.AI_ML, "curated", relevance=0.6),
    KnowledgeTerm("machine learning", ("machine learning",), "phrase",
                  Domain.AI_ML, "curated", relevance=0.6),
    KnowledgeTerm("ONNX", ("onnx", "o n n x"), "format", Domain.AI_ML,
                  "curated", relevance=0.65),
]


def _load(path: Path):
    if not path.exists():
        return []
    return [KnowledgeTerm.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def merge(groups):
    by_norm = {}
    order = []
    for terms in groups:
        for t in terms:
            key = normalize_text(t.canonical)
            if not key:
                continue
            if key not in by_norm:
                by_norm[key] = t
                order.append(key)
            else:
                # Merge variants/aliases into the first-seen term.
                existing = by_norm[key]
                merged_variants = tuple(dict.fromkeys(
                    [*existing.spoken_variants, *t.spoken_variants]))
                by_norm[key] = KnowledgeTerm(
                    canonical=existing.canonical,
                    spoken_variants=merged_variants,
                    category=existing.category, domain=existing.domain,
                    source=existing.source + "+" + t.source,
                    aliases=tuple(dict.fromkeys([*existing.aliases, *t.aliases])),
                    relevance=max(existing.relevance, t.relevance),
                    metadata=existing.metadata)
    return [by_norm[k] for k in order]


def main():
    ART.mkdir(parents=True, exist_ok=True)
    linguist = _load(INGESTED / "linguist_terms.json")
    pkgs = _load(INGESTED / "npm_pypi_terms.json")
    curated = _CURATED_TECH

    # Curated first (highest-value, exercised by corpus), then packages, then
    # the large language list.
    terms = merge([curated, pkgs, linguist])
    index = KnowledgeIndex.from_terms(terms)
    index_path = ART / "knowledge_index.json"
    index.save(index_path)

    stats = index.stats()
    stats["index_file_bytes"] = index_path.stat().st_size
    (ART / "index_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    ingestion = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "linguist_terms": len(linguist),
        "npm_pypi_terms": len(pkgs),
        "curated_tech_terms": len(curated),
        "merged_total": len(terms),
        "index_stats": stats,
    }
    (ART / "ingestion_report.json").write_text(json.dumps(ingestion, indent=2), encoding="utf-8")

    manifest = {
        "build_date": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {"source": "github-linguist/linguist", "file": "lib/linguist/languages.yml",
             "license": "MIT", "entries": len(linguist), "runtime_network": False},
            {"source": "nice-registry/all-the-package-names", "license": "MIT",
             "entries_ingested": sum(1 for t in pkgs if "npm" in t.source),
             "note": "bounded curated real subset; full 117MB LFS dataset NOT loaded"},
            {"source": "sethmlarson/pypi-data", "license": "Apache-2.0",
             "entries_ingested": sum(1 for t in pkgs if "pypi" in t.source),
             "note": "bounded curated real subset; full dataset NOT loaded"},
            {"source": "SayIt curated technical pack", "license": "project (MIT)",
             "entries": len(curated), "note": "databases/protocols/tools + corpus mis-hearings"},
        ],
        "merged_total": len(terms),
        "index_artifact": str(index_path.relative_to(ROOT)),
        "runtime_network": False,
        "embeddings": False,
    }
    (ART / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"merged {len(terms)} terms; index {stats['index_file_bytes']} bytes; "
          f"stats={stats}")


if __name__ == "__main__":
    main()
