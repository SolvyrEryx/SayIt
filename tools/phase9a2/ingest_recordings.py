"""Phase 9A.2 recording ingest — convert + validate (no mapping commit yet).

Converts the user's source .m4a recordings to the SayIt capture spec
(WAV / 16000 Hz / mono / PCM s16le) via ffmpeg into a STAGING directory, then
validates each output (container, spec, non-empty, non-silent, peak/RMS). The
original .m4a files are never modified, renamed, moved, or deleted.

Mapping to corpus clip IDs is NOT performed here — a separate verification step
transcribes the staged WAVs and matches content to references before any file
enters artifacts/phase9/9A2/corpus/.

Emits artifacts/phase9/9A2R/source_inventory.json and conversion_report.json.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = Path(r"C:\Users\user\OneDrive\Documents\Sound Recordings")
STAGE = ROOT / "artifacts" / "phase9" / "9A2R" / "staging"
OUT = ROOT / "artifacts" / "phase9" / "9A2R"

SR = 16000


def ffprobe(path: Path) -> dict:
    ff = shutil.which("ffprobe")
    if not ff:
        return {}
    try:
        p = subprocess.run(
            [ff, "-v", "error", "-show_entries",
             "stream=codec_name,sample_rate,channels:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return json.loads(p.stdout or "{}")
    except Exception as e:
        return {"error": str(e)[:120]}


def convert(src: Path, dst: Path) -> dict:
    ff = shutil.which("ffmpeg")
    if not ff:
        return {"ok": False, "error": "ffmpeg not found"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(
            [ff, "-y", "-i", str(src), "-ac", "1", "-ar", str(SR),
             "-sample_fmt", "s16", "-f", "wav", str(dst)],
            capture_output=True, text=True, timeout=120,
        )
        if p.returncode != 0:
            return {"ok": False, "error": p.stderr[-200:]}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def validate_wav(path: Path) -> dict:
    try:
        w = wave.open(str(path), "rb")
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
        w.close()
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        dur = n / sr if sr else 0.0
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
        spec_ok = sr == SR and ch == 1 and width == 2
        non_silent = peak > 0.02 and rms > 0.001
        return {
            "sample_rate": sr, "channels": ch, "sampwidth_bytes": width,
            "duration_s": round(dur, 3), "peak": round(peak, 4), "rms": round(rms, 5),
            "spec_ok": spec_ok, "non_silent": non_silent,
            "valid": spec_ok and non_silent and dur > 0.3,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)[:160]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    sources = sorted(
        [p for p in SRC_DIR.glob("*") if p.suffix.lower() == ".m4a"]
    )
    inventory = []
    conversions = []
    for src in sources:
        stat = src.stat()
        probe = ffprobe(src)
        # Stage filename = sanitized source stem.
        stem = src.stem.replace(" ", "_").replace("-", "").replace("__", "_")
        dst = STAGE / f"{stem}.wav"
        conv = convert(src, dst)
        val = validate_wav(dst) if conv.get("ok") else {"valid": False}
        inventory.append({
            "source_filename": src.name,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
            "probe": probe,
            "staged_wav": str(dst.relative_to(ROOT)),
        })
        conversions.append({
            "source_filename": src.name,
            "staged_wav": dst.name,
            "conversion": conv,
            "validation": val,
        })

    (OUT / "source_inventory.json").write_text(
        json.dumps({"source_dir": str(SRC_DIR), "count": len(sources),
                    "files": inventory}, indent=2), encoding="utf-8")
    (OUT / "conversion_report.json").write_text(
        json.dumps({"count": len(conversions), "conversions": conversions}, indent=2),
        encoding="utf-8")

    valid = sum(1 for c in conversions if c["validation"].get("valid"))
    print(f"converted={len(conversions)} valid={valid} staged_in={STAGE}")
    for c in conversions:
        v = c["validation"]
        print(f"  {c['source_filename']:28s} -> {c['staged_wav']:24s} "
              f"valid={v.get('valid')} dur={v.get('duration_s')} "
              f"sr={v.get('sample_rate')} ch={v.get('channels')} peak={v.get('peak')}")


if __name__ == "__main__":
    main()
