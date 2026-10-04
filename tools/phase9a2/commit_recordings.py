"""Phase 9A.2 — content-verified remap + commit of real recordings.

The content verification (verify_mapping.py) showed the user's recordings do NOT
follow the prior labels.json pair order. By transcript content the recorded set
is the master-prompt section-8 discriminator list:

  Pair1 = FASTAPI    (ordinary "fast API" / technical FastAPI)
  Pair2 = PG         (postgres / PostgreSQL)
  Pair3 = OPENAI     (open AI / OpenAI)
  Pair4 = NEXTJS     (next JS / Next.js)
  Pair5 = SQLALCHEMY (sql alchemy / SQLAlchemy)
  Pair6 = TENSORFLOW (tensor flow / TensorFlow)
  Pair7 = WEBAUTHN   (web auth n / WebAuthn)
  Pair8 = KUBECTL    (kube control / kubectl)
  Multi-word = MULTI01 ; Mixed = MIXED01

PYTHON and RUST were NOT recorded. This is reported, not hidden.

This script copies the staged WAVs into artifacts/phase9/9A2/corpus/ under
CORRECTED, content-matched clip IDs, and writes labels.json entries whose
target_terms / negative_terms reflect the true discriminator. References are the
canonical intended sentences for each discriminator (ground truth for what was
asked to be recorded); the transcript is retained in mapping_review for audit.
Original .m4a and staged WAVs are untouched.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "artifacts" / "phase9" / "9A2R" / "staging"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
OUT = ROOT / "artifacts" / "phase9" / "9A2R"

# staged stem -> (clip_id, reference, target_terms, negative_terms, category, pair_id, pair_role)
MAP = [
    ("Pair1_ordinary", "PAIR_FASTAPI_ORDINARY",
     "I need a fast API for the service.", [], ["FastAPI"], "hard_negative", "FASTAPI", "ordinary"),
    ("Pair1_Technical", "PAIR_FASTAPI_TECHNICAL",
     "Build the endpoint with FastAPI and Pydantic.", ["FastAPI"], [], "hard_negative", "FASTAPI", "technical"),
    ("Pair2_ordinary", "PAIR_PG_ORDINARY",
     "The postgres server is running on the local machine.", [], ["PostgreSQL"], "hard_negative", "PG", "ordinary"),
    ("Pair2_technical", "PAIR_PG_TECHNICAL",
     "The PostgreSQL server is running on the local machine.", ["PostgreSQL"], [], "hard_negative", "PG", "technical"),
    ("Pair3_ordinary", "PAIR_OPENAI_ORDINARY",
     "We should open AI research notes and review them later.", [], ["OpenAI"], "hard_negative", "OPENAI", "ordinary"),
    ("Pair3_technical", "PAIR_OPENAI_TECHNICAL",
     "We should use OpenAI for the research task.", ["OpenAI"], [], "hard_negative", "OPENAI", "technical"),
    ("Pair4_ordinary", "PAIR_NEXTJS_ORDINARY",
     "I need the next JS example from the documentation.", [], ["Next.js"], "hard_negative", "NEXTJS", "ordinary"),
    ("Pair4_technical", "PAIR_NEXTJS_TECHNICAL",
     "I need the Next.js example from the documentation.", ["Next.js"], [], "hard_negative", "NEXTJS", "technical"),
    ("Pair5_ordinary", "PAIR_SQLALCHEMY_ORDINARY",
     "The sql alchemy diagram is in the project notes.", [], ["SQLAlchemy"], "hard_negative", "SQLALCHEMY", "ordinary"),
    ("Pair5_technical", "PAIR_SQLALCHEMY_TECHNICAL",
     "The SQLAlchemy models are in the project.", ["SQLAlchemy"], [], "hard_negative", "SQLALCHEMY", "technical"),
    ("Pair6_ordinary", "PAIR_TENSORFLOW_ORDINARY",
     "The tensor flow through the network is increasing.", [], ["TensorFlow"], "hard_negative", "TENSORFLOW", "ordinary"),
    ("Pair6_technical", "PAIR_TENSORFLOW_TECHNICAL",
     "The TensorFlow model is training correctly.", ["TensorFlow"], [], "hard_negative", "TENSORFLOW", "technical"),
    ("Pair7_ordinary", "PAIR_WEBAUTHN_ORDINARY",
     "The web auth in the documentation needs to be updated.", [], ["WebAuthn"], "hard_negative", "WEBAUTHN", "ordinary"),
    ("Pair7_technical", "PAIR_WEBAUTHN_TECHNICAL",
     "The application uses WebAuthn for authentication.", ["WebAuthn"], [], "hard_negative", "WEBAUTHN", "technical"),
    ("Pair8_ordinary", "PAIR_KUBECTL_ORDINARY",
     "We need tube control over the cluster configuration.", [], ["kubectl"], "hard_negative", "KUBECTL", "ordinary"),
    ("Pair8_technical", "PAIR_KUBECTL_TECHNICAL",
     "We use kubectl to manage the cluster.", ["kubectl"], [], "hard_negative", "KUBECTL", "technical"),
    ("Multiword", "MULTI01",
     "Configure GitHub Actions and Docker Compose for the pipeline.", [], [], "multiword", None, None),
    ("Mixed", "MIXED01",
     "I used Python yesterday, but today I need a fast API for the internal service.",
     ["Python"], ["FastAPI"], "mixed", None, None),
]
# MULTI01 phrase targets:
PHRASE = {"MULTI01": ["GitHub Actions", "Docker Compose"]}


def main():
    CORPUS.mkdir(parents=True, exist_ok=True)
    entries = json.loads(LABELS.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in entries}
    # IDs that existed in the old label set but are NOT recorded (PYTHON/RUST).
    recorded_ids = {m[1] for m in MAP}
    not_recorded = [e["id"] for e in entries
                    if e.get("needs_recording") and e["id"] not in recorded_ids
                    and e["id"] not in ("MULTI01", "MIXED01")]

    committed = []
    new_entries = []
    # Keep the real A-E as-is.
    for e in entries:
        if e["id"] in ("A", "B", "C", "D", "E"):
            new_entries.append(e)

    for stem, cid, ref, targets, negs, cat, pid, role in MAP:
        src = STAGE / f"{stem}.wav"
        dst = CORPUS / f"{cid}.wav"
        shutil.copyfile(src, dst)
        entry = {
            "id": cid, "wav": f"{cid}.wav", "reference": ref,
            "target_terms": targets, "negative_terms": negs,
            "category": cat, "synthetic": False, "needs_recording": False,
            "source": "user_recording_2026-10-03",
        }
        if pid:
            entry["pair_id"] = pid
            entry["pair_role"] = role
        if cid in PHRASE:
            entry["phrase_terms"] = PHRASE[cid]
        new_entries.append(entry)
        committed.append({"stem": stem, "id": cid, "wav": str(dst.relative_to(ROOT))})

    # Preserve PYTHON/RUST template rows (still needs_recording) for honesty.
    for e in entries:
        if e["id"] in not_recorded:
            new_entries.append(e)

    LABELS.write_text(json.dumps(new_entries, indent=2), encoding="utf-8")

    report = {
        "committed_count": len(committed),
        "committed": committed,
        "recorded_discriminators": sorted({m[6] for m in MAP if m[6]}),
        "not_recorded_pairs": not_recorded,
        "note": "User's recorded set matches master-prompt section-8 discriminators "
                "(FASTAPI/PG/OPENAI/NEXTJS/SQLALCHEMY/TENSORFLOW/WEBAUTHN/KUBECTL), "
                "NOT the prior labels.json pairs (which included PYTHON/RUST and no "
                "SQLALCHEMY/WEBAUTHN). Mapping was corrected by transcript content, "
                "not by assuming filename order.",
    }
    (OUT / "commit_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"committed={len(committed)} not_recorded_pairs={not_recorded}")


if __name__ == "__main__":
    main()
