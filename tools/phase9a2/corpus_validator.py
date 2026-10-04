"""Phase 9A.2 — corpus schema + validator.

The labels file is a JSON list of entries. Each entry:

    {
      "id": "A",                      # stable id; <id>.wav must exist OR be
                                      #   marked needs_recording=True
      "reference": "....",            # exact intended transcript (immutable for A-E)
      "target_terms": ["PostgreSQL"], # terms that MUST be recognized (may be [])
      "negative_terms": ["FastAPI"],  # terms that MUST NOT appear (may be [])
      "category": "technical",        # one of CATEGORIES
      "synthetic": false,             # true only for local-TTS clips (none here)
      "pair_id": "PG",                # optional: links a hard-negative pair
      "pair_role": "ordinary",        # optional: 'ordinary' | 'technical'
      "needs_recording": false,       # true => audio not yet captured (template)
      "wav": "A.wav"                  # optional explicit filename; defaults <id>.wav
    }

The validator never raises on content; it returns a structured error list so the
benchmark can skip invalid/needs-recording entries deterministically.
"""

from __future__ import annotations

from typing import Dict, List

CATEGORIES = {
    "ordinary",
    "technical",
    "package",
    "acronym",
    "multiword",
    "hard_negative",
    "mixed",
}

REQUIRED_KEYS = {"id", "reference", "target_terms", "negative_terms", "category", "synthetic"}


def validate_entry(entry: Dict) -> List[str]:
    errors: List[str] = []
    missing = REQUIRED_KEYS - set(entry)
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
        return errors
    if not isinstance(entry["id"], str) or not entry["id"].strip():
        errors.append("id must be a non-empty string")
    if not isinstance(entry["reference"], str) or not entry["reference"].strip():
        errors.append("reference must be a non-empty string")
    if not isinstance(entry["target_terms"], list):
        errors.append("target_terms must be a list")
    if not isinstance(entry["negative_terms"], list):
        errors.append("negative_terms must be a list")
    if entry["category"] not in CATEGORIES:
        errors.append(f"category must be one of {sorted(CATEGORIES)}")
    if not isinstance(entry["synthetic"], bool):
        errors.append("synthetic must be a bool")
    return errors


def validate_corpus(entries: List[Dict]) -> Dict:
    """Validate the whole corpus. Returns a structured summary."""
    ids = set()
    per_entry = {}
    dup = []
    for e in entries:
        errs = validate_entry(e)
        eid = e.get("id", "?")
        if eid in ids:
            dup.append(eid)
        ids.add(eid)
        if errs:
            per_entry[eid] = errs
    return {
        "total": len(entries),
        "valid": len(entries) - len(per_entry) - len(dup),
        "errors": per_entry,
        "duplicate_ids": sorted(dup),
        "ok": not per_entry and not dup,
    }


def scored_entries(entries: List[Dict]) -> List[Dict]:
    """Entries that can actually be scored now: valid, not needing recording,
    and either real audio present (checked by caller) — here we filter out the
    needs_recording template rows."""
    out = []
    for e in entries:
        if validate_entry(e):
            continue
        if e.get("needs_recording", False):
            continue
        out.append(e)
    return out
