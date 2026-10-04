"""Phase 11A — TIE_shorts acquisition (TEMPORARY env only).

Runs in the isolated acquisition venv (tools/phase11a/.venv-acq) which has
`datasets`/`soundfile`/`librosa` + `huggingface_hub`. It:
  1. reads TIE_shorts Metadata.csv,
  2. deterministically selects a diversity-aware subset (cap per speaker;
     spread across disciplines/regions; manageable count),
  3. downloads ONLY the selected mp3s,
  4. converts each to WAV mono/16 kHz/PCM (deterministic filename),
  5. stages artifacts/phase10/external/tie_shorts/{audio, manifest.csv},
  6. validates integrity.

References are preserved verbatim (the 'Transcript' column). SayIt itself never
imports datasets/librosa; this is one-time staging.

Deterministic selection rule (documented): sort rows by (ID); then round-robin
across (Speaker ID) with a per-speaker cap, up to MAX_CLIPS, preferring clips
with non-trivial transcript length and valid duration.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
from huggingface_hub import hf_hub_download

REPO = "raianand/TIE_shorts"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "phase10" / "external" / "tie_shorts"
AUDIO = OUT / "audio"
MAX_CLIPS = 120
PER_SPEAKER_CAP = 8
MIN_WORDS = 5
MAX_DUR = 30.0


def select(rows):
    # Deterministic ordering.
    rows = sorted(rows, key=lambda r: str(r.get("ID", "")))
    by_speaker = defaultdict(list)
    for r in rows:
        tr = (r.get("Transcript") or "").strip()
        try:
            dur = float(r.get("Speech Duration (seconds)") or 0)
        except Exception:
            dur = 0.0
        if len(tr.split()) < MIN_WORDS or dur <= 0 or dur > MAX_DUR:
            continue
        by_speaker[str(r.get("Speaker ID", "?"))].append(r)
    # Round-robin across speakers (sorted) with a per-speaker cap.
    speakers = sorted(by_speaker)
    picked = []
    idx = 0
    while len(picked) < MAX_CLIPS:
        advanced = False
        for sp in speakers:
            lst = by_speaker[sp]
            if idx < min(len(lst), PER_SPEAKER_CAP):
                picked.append(lst[idx])
                advanced = True
                if len(picked) >= MAX_CLIPS:
                    break
        if not advanced:
            break
        idx += 1
    return picked


def main():
    AUDIO.mkdir(parents=True, exist_ok=True)
    meta = hf_hub_download(REPO, "Metadata.csv", repo_type="dataset")
    rows = list(csv.DictReader(open(meta, encoding="utf-8", errors="replace")))
    picked = select(rows)
    print(f"selected {len(picked)} clips from {len({r['Speaker ID'] for r in picked})} speakers")

    manifest_rows = []
    for r in picked:
        rid = str(r["ID"])
        try:
            mp3 = hf_hub_download(REPO, r["audio_path"], repo_type="dataset")
        except Exception as e:
            print("skip (download fail):", rid, str(e)[:60])
            continue
        try:
            y, sr = librosa.load(mp3, sr=16000, mono=True)
            if y.size < 1600:
                print("skip (too short):", rid)
                continue
            wav = AUDIO / f"{rid}.wav"
            sf.write(str(wav), (y * 32767).astype(np.int16), 16000, subtype="PCM_16")
        except Exception as e:
            print("skip (convert fail):", rid, str(e)[:60])
            continue
        manifest_rows.append({
            "sample_id": rid,
            "speaker_id": str(r.get("Speaker ID", "?")),
            "text": (r.get("Transcript") or "").strip(),
            "audio": f"audio/{rid}.wav",
            "discipline": r.get("Discipline Group", ""),
            "region": r.get("Native Region", ""),
            "gender": r.get("Gender", ""),
        })

    manifest_rows.sort(key=lambda x: x["sample_id"])
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sample_id", "speaker_id", "text", "audio",
                                          "discipline", "region", "gender"])
        w.writeheader()
        w.writerows(manifest_rows)
    print(f"staged {len(manifest_rows)} clips -> {OUT}")


if __name__ == "__main__":
    main()
