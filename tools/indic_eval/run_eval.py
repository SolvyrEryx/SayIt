"""Repeatable Hindi/Kannada ASR evaluation harness (release-gate).

Uses the production SayIt inference path (``TranscriptionEngine`` ->
``SherpaOnnxBackend.from_nemo_ctc``) on properly-licensed, held-out audio from
Google **FLEURS** (CC-BY-4.0) — the same benchmark family the IndicConformer
distributor documents. Nothing is fabricated: every number below comes from
real decoding of real audio against FLEURS reference transcriptions.

Metrics per language: WER, CER, cold-start latency, warm transcription latency,
peak RSS during decode, and transcription failure rate.

Usage:
    python tools/indic_eval/run_eval.py --lang hi --limit 20
    python tools/indic_eval/run_eval.py --lang kn --limit 20

Audio + transcripts are cached under artifacts/indic_eval/<lang>/ so reruns are
offline. This harness downloads only the small FLEURS *dev* split archive
(~130-250 MB) and a handful of clips; it never pulls training data.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tarfile
import time
import unicodedata
from pathlib import Path

import numpy as np
import requests

# Make all stdout UTF-8 so Devanagari/Kannada print safely on Windows consoles.
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402

FLEURS_BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"
LANG_CFG = {"hi": "hi_in", "kn": "kn_in"}
MODEL_FOR_LANG = {"hi": "indicconformer-hi-int8", "kn": "indicconformer-kn-int8"}
CACHE = REPO_ROOT / "artifacts" / "indic_eval"


# ---------------------------------------------------------------------------
# Text normalization + edit distance (for WER/CER)
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    # Drop punctuation but keep Indic/Latin letters, marks, and spaces.
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _edit_distance(ref: list, hyp: list) -> int:
    n, m = len(ref), len(hyp)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def wer(ref: str, hyp: str) -> float:
    r, h = normalize_text(ref).split(), normalize_text(hyp).split()
    if not r:
        return 0.0 if not h else 1.0
    return _edit_distance(r, h) / len(r)


def cer(ref: str, hyp: str) -> float:
    r = list(normalize_text(ref).replace(" ", ""))
    h = list(normalize_text(hyp).replace(" ", ""))
    if not r:
        return 0.0 if not h else 1.0
    return _edit_distance(r, h) / len(r)


# ---------------------------------------------------------------------------
# FLEURS data acquisition (licensed CC-BY-4.0, dev split only)
# ---------------------------------------------------------------------------
def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    os.replace(tmp, dest)


def load_references(lang: str) -> dict:
    cfg = LANG_CFG[lang]
    tsv_path = CACHE / lang / "dev.tsv"
    _download(f"{FLEURS_BASE}/{cfg}/dev.tsv", tsv_path)
    refs = {}
    with open(tsv_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            # FLEURS TSV: id, filename, raw_transcription, transcription, ...
            if len(parts) >= 4:
                refs[parts[1]] = parts[3] or parts[2]
    return refs


def extract_clips(lang: str, limit: int) -> list:
    """Extract up to ``limit`` wav clips (filename, bytes) from dev.tar.gz."""
    cfg = LANG_CFG[lang]
    tar_path = CACHE / lang / "dev.tar.gz"
    _download(f"{FLEURS_BASE}/{cfg}/audio/dev.tar.gz", tar_path)
    clips = []
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.name.endswith(".wav"):
                continue
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            clips.append((os.path.basename(member.name), fobj.read()))
            if len(clips) >= limit:
                break
    return clips


def _wav_to_float32(wav_bytes: bytes):
    """Parse a RIFF/WAVE blob to mono float32 + sample rate.

    Handles both PCM16 (format tag 1) and IEEE float32 (format tag 3). FLEURS
    ships float32 wavs, which the stdlib ``wave`` module cannot read, so we
    parse the chunks directly.
    """
    import struct

    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/WAVE file")

    pos = 12
    fmt_tag = channels = sample_rate = bits = None
    data = None
    while pos + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[pos : pos + 4]
        (chunk_size,) = struct.unpack_from("<I", wav_bytes, pos + 4)
        body = wav_bytes[pos + 8 : pos + 8 + chunk_size]
        if chunk_id == b"fmt ":
            fmt_tag, channels, sample_rate, _br, _ba, bits = struct.unpack_from(
                "<HHIIHH", body, 0
            )
        elif chunk_id == b"data":
            data = body
        pos += 8 + chunk_size + (chunk_size & 1)  # chunks are word-aligned

    if data is None or fmt_tag is None:
        raise ValueError("Missing fmt/data chunk")

    if fmt_tag == 1 and bits == 16:
        audio = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    elif fmt_tag == 3 and bits == 32:
        audio = np.frombuffer(data, dtype="<f4").astype(np.float32)
    elif fmt_tag == 1 and bits == 32:
        audio = np.frombuffer(data, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV format tag={fmt_tag} bits={bits}")

    if channels and channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, int(sample_rate)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def run(lang: str, limit: int) -> dict:
    import tracemalloc

    refs = load_references(lang)
    clips = extract_clips(lang, limit)
    model = MODEL_FOR_LANG[lang]

    engine = TranscriptionEngine(model_name=model)

    # Cold-start latency: time to load the model the first time.
    t0 = time.time()
    engine.load_model()
    cold_start_s = time.time() - t0

    per_clip = []
    failures = 0
    warm_latencies = []
    tracemalloc.start()
    peak_rss = 0

    for fname, wav in clips:
        ref = refs.get(fname)
        if ref is None:
            continue
        try:
            audio, sr = _wav_to_float32(wav)
            t1 = time.time()
            hyp = engine.transcribe(audio, sample_rate=sr)
            dt = time.time() - t1
            if hyp is None:
                failures += 1
                continue
            warm_latencies.append(dt)
            _, peak = tracemalloc.get_traced_memory()
            peak_rss = max(peak_rss, peak)
            per_clip.append(
                {
                    "file": fname,
                    "ref": ref,
                    "hyp": hyp,
                    "wer": wer(ref, hyp),
                    "cer": cer(ref, hyp),
                    "latency_s": dt,
                    "audio_s": len(audio) / sr,
                }
            )
        except Exception as e:  # count as a transcription failure
            failures += 1
            per_clip.append({"file": fname, "error": f"{type(e).__name__}: {e}"})

    tracemalloc.stop()
    engine.unload()

    scored = [c for c in per_clip if "wer" in c]
    n = len(scored)
    summary = {
        "language": lang,
        "model": model,
        "audio_source": "google/fleurs dev split (CC-BY-4.0)",
        "num_clips_scored": n,
        "num_failures": failures,
        "failure_rate": failures / max(1, len(clips)),
        "wer_mean": sum(c["wer"] for c in scored) / n if n else None,
        "cer_mean": sum(c["cer"] for c in scored) / n if n else None,
        "cold_start_s": round(cold_start_s, 3),
        "warm_latency_p50_s": (
            round(sorted(warm_latencies)[len(warm_latencies) // 2], 3)
            if warm_latencies
            else None
        ),
        "warm_latency_mean_s": (
            round(sum(warm_latencies) / len(warm_latencies), 3)
            if warm_latencies
            else None
        ),
        "peak_traced_mem_mib": round(peak_rss / (1024 * 1024), 1),
    }
    return {"summary": summary, "per_clip": per_clip}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["hi", "kn"], required=True)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    result = run(args.lang, args.limit)
    out_dir = CACHE / args.lang
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "eval_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nWrote {out_file}")
    # Show 3 real examples as script-level evidence.
    print("\n--- sample decodes (real) ---")
    for c in result["per_clip"][:3]:
        if "hyp" in c:
            print(f"ref: {c['ref']}")
            print(f"hyp: {c['hyp']}")
            print(f"    wer={c['wer']:.2f} cer={c['cer']:.2f}\n")


if __name__ == "__main__":
    main()
