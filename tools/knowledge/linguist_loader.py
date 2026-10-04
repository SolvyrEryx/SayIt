"""Phase 9C build-time ingester — GitHub Linguist languages.yml.

Downloads the single structured data file (lib/linguist/languages.yml) at
BUILD/DEV time only and extracts language names + aliases + interpreters into
KnowledgeTerm records. The Linguist project's own code/data files are MIT
licensed (bundled grammars have their own licenses, which we do NOT ingest —
only the structured languages.yml fields). Runtime SayIt never contacts the
network; this tool produces a local artifact.

Usage:
    uv run python tools/knowledge/linguist_loader.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.knowledge.models import Domain, KnowledgeTerm  # noqa: E402

LANGUAGES_YML_URL = (
    "https://raw.githubusercontent.com/github-linguist/linguist/"
    "master/lib/linguist/languages.yml"
)
OUT = ROOT / "artifacts" / "phase9" / "9C" / "ingested"


def fetch_yaml(url: str = LANGUAGES_YML_URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "SayIt-9C-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_languages(text: str):
    import yaml

    data = yaml.safe_load(text)
    terms = []
    for name, info in (data or {}).items():
        if not isinstance(info, dict):
            continue
        lang_type = info.get("type", "")
        # Keep programming/markup languages; skip "data"/"prose" noise.
        if lang_type not in ("programming", "markup"):
            continue
        aliases = [str(a) for a in (info.get("aliases") or [])]
        interpreters = [str(a) for a in (info.get("interpreters") or [])]
        terms.append(KnowledgeTerm(
            canonical=str(name),
            spoken_variants=tuple(aliases),
            category="language",
            domain=Domain.DEVELOPER,
            source="linguist",
            aliases=tuple(interpreters),
            relevance=0.6,
            metadata={"linguist_type": lang_type},
        ))
    return terms


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    text = fetch_yaml()
    terms = parse_languages(text)
    out_file = OUT / "linguist_terms.json"
    out_file.write_text(
        json.dumps([t.to_dict() for t in terms], indent=2), encoding="utf-8"
    )
    manifest = {
        "source": "github-linguist/linguist",
        "file": "lib/linguist/languages.yml",
        "url": LANGUAGES_YML_URL,
        "license": "MIT (languages.yml structured fields only; bundled grammars not ingested)",
        "entry_count": len(terms),
        "fields_used": ["name", "aliases", "interpreters", "type"],
        "transformation": "programming/markup languages -> KnowledgeTerm(category=language)",
        "bundled": "generated local artifact (not committed to source tree by default)",
    }
    (OUT / "linguist_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"linguist: {len(terms)} language terms -> {out_file}")


if __name__ == "__main__":
    main()
