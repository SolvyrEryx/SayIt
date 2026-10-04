"""Phase 9C build-time ingester — curated npm / PyPI package subset.

The full npm name list (all-the-package-names, ~286k names) ships as a 117 MB
git-LFS file. Per the phase rules (sections 12 and 32) we must NOT load the whole
dataset into memory or feed it to the corrector. Full dataset ingestion into a
disk-backed index is a legitimate FUTURE build-tooling task; for the 9C
retrieval-architecture proof we ingest a BOUNDED, hand-reviewed subset of REAL,
well-known package names (both npm and PyPI). These are real package names from
the public registries; provenance and the deferral of full ingestion are
recorded in the manifest.

Usage:
    uv run python tools/knowledge/npm_pypi_seed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.knowledge.models import Domain, KnowledgeTerm  # noqa: E402

OUT = ROOT / "artifacts" / "phase9" / "9C" / "ingested"

# Real, well-known npm package names (bounded curated subset of the public npm
# registry). Canonical form is the published package name.
_NPM = [
    ("react", "framework"), ("next", "framework"), ("express", "framework"),
    ("vue", "framework"), ("webpack", "tool"), ("vite", "tool"),
    ("typescript", "language"), ("eslint", "tool"), ("prettier", "tool"),
    ("axios", "library"), ("lodash", "library"), ("jest", "tool"),
    ("tailwindcss", "framework"), ("redux", "library"), ("nestjs", "framework"),
]

# Real, well-known PyPI package names (bounded curated subset).
_PYPI = [
    ("fastapi", "framework"), ("pydantic", "library"), ("sqlalchemy", "library"),
    ("numpy", "library"), ("pandas", "library"), ("scikit-learn", "library"),
    ("transformers", "library"), ("sentence-transformers", "library"),
    ("opencv-python", "library"), ("django", "framework"), ("flask", "framework"),
    ("requests", "library"), ("torch", "library"), ("tensorflow", "library"),
    ("onnx", "library"), ("langchain", "library"), ("uvicorn", "tool"),
    ("pytest", "tool"), ("rapidfuzz", "library"), ("platformdirs", "library"),
]

# A small spoken-variant map for packages whose spoken form differs notably.
_VARIANTS = {
    "fastapi": ("fast api", "fastapi"),
    "sqlalchemy": ("sql alchemy", "sqlalchemy"),
    "scikit-learn": ("scikit learn", "sklearn", "scikit-learn"),
    "opencv-python": ("opencv python", "open cv", "opencv"),
    "sentence-transformers": ("sentence transformers",),
    "tensorflow": ("tensor flow", "tensorflow"),
    "nestjs": ("nest js", "nestjs"),
    "next": ("next js", "nextjs", "next.js"),
    "torch": ("pytorch", "torch", "pie torch"),
}


def _mk(name, category, source, domain):
    variants = _VARIANTS.get(name, (name,))
    return KnowledgeTerm(
        canonical=name, spoken_variants=tuple(variants), category=category,
        domain=domain, source=source, relevance=0.55,
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    terms = [_mk(n, c, "npm", Domain.DEVELOPER) for n, c in _NPM]
    terms += [_mk(n, c, "pypi", Domain.DEVELOPER) for n, c in _PYPI]
    (OUT / "npm_pypi_terms.json").write_text(
        json.dumps([t.to_dict() for t in terms], indent=2), encoding="utf-8")
    manifest = {
        "sources": [
            {"source": "nice-registry/all-the-package-names", "license": "MIT",
             "data": "names.json (117 MB git-LFS)",
             "ingested": "BOUNDED curated real subset (15 npm names)",
             "note": "Full dataset NOT loaded per phase rules 12/32; full "
                     "disk-backed ingestion deferred to future build tooling."},
            {"source": "sethmlarson/pypi-data", "license": "Apache-2.0",
             "data": "package names/metadata",
             "ingested": "BOUNDED curated real subset (20 PyPI names)",
             "note": "Full dataset NOT loaded; deferred."},
        ],
        "npm_count": len(_NPM),
        "pypi_count": len(_PYPI),
        "total": len(terms),
    }
    (OUT / "npm_pypi_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"npm+pypi curated: {len(terms)} terms -> {OUT / 'npm_pypi_terms.json'}")


if __name__ == "__main__":
    main()
