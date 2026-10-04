"""Phase 9A.2R — recording ingest / status checker.

Makes the record -> ingest -> re-run loop turnkey. For each labels.json entry it
checks whether the audio file now exists, validates it against SayIt's capture
spec (mono, 16000 Hz, 16-bit PCM WAV), and reports a precise status. It can
optionally auto-flip ``needs_recording`` to false for entries whose VALID audio
is now present, so re-running the 9A.2 benchmark immediately includes them.

It NEVER creates, fabricates, or synthesizes speech. It only inspects files a
human has placed in the corpus directory. Pure/deterministic apart from the
explicit --apply write.

Usage:
    uv run python tools/phase9a2/ingest_status.py            # report only
    uv run python tools/phase9a2/ingest_status.py --apply    # also update labels
    uv run python tools/phase9a2/ingest_status.py --out <status.json>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"

SPEC = {"sample_rate": 16000, "channels": 1, "sampwidth_bytes": 2}


def wav_spec(path: Path) -> dict:
    try:
        w = wave.open(str(path), "rb")
        info = {
            "sample_rate": w.getframerate(),
            "channels": w.getnchannels(),
            "sampwidth_bytes": w.getsampwidth(),
            "frames": w.getnframes(),
        }
        w.close()
        info["duration_s"] = round(info["frames"] / info["sample_rate"], 3) if info["sample_rate"] else None
        info["spec_ok"] = (
            info["sample_rate"] == SPEC["sample_rate"]
            and info["channels"] == SPEC["channels"]
            and info["sampwidth_bytes"] == SPEC["sampwidth_bytes"]
        )
        return info
    except Exception as e:
        return {"error": str(e)[:160], "spec_ok": False}


def find_wav(entry: dict):
    wav = entry.get("wav", entry["id"] + ".wav")
    for base in (CORPUS, EVAL):
        p = base / wav
        if p.exists():
            return p
    return None


def build_status(entries):
    rows = []
    present = valid = missing = invalid = 0
    for e in entries:
        p = find_wav(e)
        row = {
            "id": e["id"],
            "category": e["category"],
            "needs_recording_flag": e.get("needs_recording", False),
            "audio_present": p is not None,
            "path": str(p) if p else None,
        }
        if p is not None:
            spec = wav_spec(p)
            row["spec"] = spec
            present += 1
            if spec.get("spec_ok"):
                valid += 1
            else:
                invalid += 1
        else:
            missing += 1
        rows.append(row)
    # The clips that still block a complete evaluation.
    blocking = [
        r["id"] for r in rows
        if r["needs_recording_flag"] and not (r["audio_present"] and r["spec"].get("spec_ok"))
    ] if rows else []
    return {
        "total": len(entries),
        "audio_present": present,
        "valid_spec": valid,
        "invalid_spec": invalid,
        "missing": missing,
        "blocking_ids": blocking,
        "recording_complete": len(blocking) == 0,
        "rows": rows,
    }


def apply_updates(entries, status):
    """Flip needs_recording=false for entries whose valid audio is now present.
    Returns the number of entries updated."""
    by_id = {r["id"]: r for r in status["rows"]}
    updated = 0
    for e in entries:
        r = by_id.get(e["id"])
        if not r:
            continue
        if e.get("needs_recording", False) and r["audio_present"] and r.get("spec", {}).get("spec_ok"):
            e["needs_recording"] = False
            updated += 1
    return updated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="flip needs_recording=false where valid audio exists")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "phase9" / "9A2R" / "recording_status.json"))
    args = ap.parse_args()

    entries = json.loads(LABELS.read_text(encoding="utf-8"))
    status = build_status(entries)

    if args.apply:
        n = apply_updates(entries, status)
        LABELS.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        status["applied_updates"] = n
        # Recompute after applying so the report reflects the new flags.
        status = build_status(entries)
        status["applied_updates"] = n

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"recording_complete={status['recording_complete']} "
          f"present={status['audio_present']} valid={status['valid_spec']} "
          f"missing={status['missing']} blocking={len(status['blocking_ids'])}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
