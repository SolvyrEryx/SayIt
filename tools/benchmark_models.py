"""Local ASR model benchmark (Phase 6D).

Measures, for one or more installed SayIt models, the mechanical facts:
install/load/inference/latency/RAM, plus WER against any reference transcripts.
Everything is local; no cloud, no LLM, no mocks. Transcripts for the shared
benchmark clips are written to the artifacts JSON (a controlled local store),
NOT through the application's normal logging.

Shared audio for a fair comparison:
- The LibriSpeech clips bundled with Whisper Tiny (``test_wavs/`` + ``trans.txt``)
  are used as the common real-speech set with ground-truth references.
- Any user WAVs dropped into ``artifacts/phase6/eval-audio/`` are ALSO run
  through every model (put an optional ``refs.txt`` there as "<file> <reference>"
  lines to get WER; without it, transcripts are preserved for manual review).

Usage:
    uv run python tools/benchmark_models.py <model_id> [<model_id> ...]
    uv run python tools/benchmark_models.py --all
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

# Make src importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.models.registry import (  # noqa: E402
    AVAILABLE_MODELS,
    is_model_downloaded,
)
from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402

ART = Path("artifacts/phase6/model-benchmark")
EVAL_AUDIO = Path("artifacts/phase6/eval-audio")


def _normalize(text: str):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def wer(reference: str, hypothesis: str):
    r, h = _normalize(reference), _normalize(hypothesis)
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[len(r)][len(h)], len(r)


def _read_wav(path: Path):
    w = wave.open(str(path), "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr, n / sr


def audio_properties(path: Path) -> dict:
    """Report WAV properties without modifying the file (Part 4 validation)."""
    try:
        w = wave.open(str(path), "rb")
        sr, n, ch, width = (
            w.getframerate(),
            w.getnframes(),
            w.getnchannels(),
            w.getsampwidth(),
        )
        raw = w.readframes(n)
        w.close()
        if width == 2:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            arr = (arr - 128) / 128.0
        if ch > 1 and arr.size:
            arr = arr.reshape(-1, ch)[:, 0]
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
        return {
            "file": path.name,
            "sample_rate": sr,
            "channels": ch,
            "bit_depth": width * 8,
            "duration_s": round(n / sr, 2) if sr else None,
            "sample_count": n,
            "peak": round(peak, 4),
            "rms": round(rms, 4),
            "appears_silent": peak < 0.01,
            "clipping_detected": peak >= 0.999,
            "asr_ready_16k_mono": (sr == 16000 and ch == 1 and width == 2),
        }
    except Exception as e:  # noqa: BLE001
        return {"file": path.name, "error": f"{type(e).__name__}: {e}"}


def _rss_mb():
    try:
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wt.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wt.HANDLE,
            ctypes.POINTER(PMC),
            wt.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wt.BOOL

        c = PMC()
        c.cb = ctypes.sizeof(c)
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
        )
        if not ok:
            return None
        return round(c.WorkingSetSize / 1024 / 1024, 1)
    except Exception:
        return None


def _collect_clips():
    """Return list of (name, path, reference_or_None). Shared across models."""
    clips = []
    # Bundled LibriSpeech (reference available).
    tiny_dir = Path(get_models_dir()) / "sherpa-onnx-whisper-tiny" / "test_wavs"
    refs = {}
    tp = tiny_dir / "trans.txt"
    if tp.exists():
        for line in tp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                fn, _, text = line.strip().partition(" ")
                refs[fn] = text
    for fn in ("0.wav", "1.wav", "8k.wav"):
        p = tiny_dir / fn
        if p.exists():
            clips.append((f"libri/{fn}", p, refs.get(fn)))
    # Optional user eval audio.
    if EVAL_AUDIO.exists():
        user_refs = {}
        rp = EVAL_AUDIO / "refs.txt"
        if rp.exists():
            for line in rp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    fn, _, text = line.strip().partition(" ")
                    user_refs[fn] = text
        for p in sorted(EVAL_AUDIO.glob("*.wav")):
            # Reference priority: refs.txt entry, else a sibling <stem>.txt.
            ref = user_refs.get(p.name)
            if ref is None:
                sidecar = p.with_suffix(".txt")
                if sidecar.exists():
                    ref = sidecar.read_text(encoding="utf-8").strip()
            clips.append((f"user/{p.name}", p, ref))
    return clips


def benchmark_model(model_id: str) -> dict:
    result = {"model_id": model_id, "installed": is_model_downloaded(model_id)}
    if not result["installed"]:
        result["status"] = "NOT INSTALLED"
        return result

    clips = _collect_clips()
    rss_before = _rss_mb()
    eng = TranscriptionEngine(model_name=model_id)
    try:
        t0 = time.perf_counter()
        eng.load_model()
        result["load_s"] = round(time.perf_counter() - t0, 2)
        result["rss_after_load_mb"] = _rss_mb()
        result["rss_before_load_mb"] = rss_before
    except Exception as e:  # noqa: BLE001
        result["status"] = f"LOAD FAILED: {type(e).__name__}: {e}"
        return result

    clip_results = []
    total_err = total_words = 0
    total_err_p = total_words_p = 0
    for name, path, ref in clips:
        try:
            audio, sr, dur = _read_wav(path)
            # Warm + timed (median of 3 for short clips).
            times = []
            hyp = ""
            for _ in range(3 if dur <= 20 else 1):
                s = time.perf_counter()
                hyp = eng.transcribe(audio, sr) or ""
                times.append(time.perf_counter() - s)

            # Phase 6G: raw vs locally-corrected transcript (same input).
            from sayit.core.transcript_processor import correct_transcript

            ps = time.perf_counter()
            processed = correct_transcript(hyp).text
            processing_s = time.perf_counter() - ps

            entry = {
                "clip": name,
                "duration_s": round(dur, 2),
                "infer_s_median": round(sorted(times)[len(times) // 2], 3),
                "processing_s": round(processing_s, 5),
                "raw_transcript": hyp,  # stored in artifacts, not app logs
                "processed_transcript": processed,
            }
            if ref:
                err, nwords = wer(ref, hyp)
                perr, pnwords = wer(ref, processed)
                entry["raw_wer_pct"] = round(err / nwords * 100, 1) if nwords else None
                entry["processed_wer_pct"] = (
                    round(perr / pnwords * 100, 1) if pnwords else None
                )
                entry["raw_edits"] = err
                entry["processed_edits"] = perr
                entry["ref_words"] = nwords
                total_err += err
                total_words += nwords
                total_err_p += perr
                total_words_p += pnwords
            clip_results.append(entry)
        except Exception as e:  # noqa: BLE001
            clip_results.append({"clip": name, "error": f"{type(e).__name__}: {e}"})

    result["clips"] = clip_results
    if total_words:
        result["overall_raw_wer_pct"] = round(total_err / total_words * 100, 1)
    if total_words_p:
        result["overall_processed_wer_pct"] = round(
            total_err_p / total_words_p * 100, 1
        )
    result["rss_peak_mb"] = _rss_mb()
    result["status"] = "OK"
    eng.unload()
    return result


def benchmark_phase6i(model_id: str) -> dict:
    """Phase 6I benchmark: raw ASR vs Phase 6G-only vs Phase 6I-full.

    For each shared clip, transcribe once (real local ASR), then run the
    corrector twice: Phase 6G-only (structured formatting disabled) and the full
    Phase 6I pipeline (structured formatting enabled). Reports WER for each stage
    where a reference exists, the applied Phase 6I transformations (rule ids and
    before/after spans), and the processing latency of each stage. Transcripts
    are written only to the artifacts JSON, never to app logs. F has no
    reference, so no F WER is computed.
    """
    from sayit.core.transcript_processor import correct_transcript

    result = {"model_id": model_id, "installed": is_model_downloaded(model_id)}
    if not result["installed"]:
        result["status"] = "NOT INSTALLED"
        return result

    clips = _collect_clips()
    eng = TranscriptionEngine(model_name=model_id)
    try:
        t0 = time.perf_counter()
        eng.load_model()
        result["load_s"] = round(time.perf_counter() - t0, 2)
    except Exception as e:  # noqa: BLE001
        result["status"] = f"LOAD FAILED: {type(e).__name__}: {e}"
        return result

    rows = []
    err_raw = w_raw = 0
    err_g = w_g = 0
    err_i = w_i = 0
    for name, path, ref in clips:
        try:
            audio, sr, dur = _read_wav(path)
            hyp = eng.transcribe(audio, sr) or ""

            g0 = time.perf_counter()
            g_res = correct_transcript(hyp, enable_structured=False)
            g_s = time.perf_counter() - g0

            i0 = time.perf_counter()
            i_res = correct_transcript(hyp, enable_structured=True)
            i_s = time.perf_counter() - i0

            i_structured = [
                {"rule": c.rule, "original": c.original, "replacement": c.replacement}
                for c in i_res.changes
                if c.category == "structured"
            ]

            row = {
                "clip": name,
                "duration_s": round(dur, 2),
                "raw_transcript": hyp,
                "phase6g_transcript": g_res.text,
                "phase6i_transcript": i_res.text,
                "phase6g_s": round(g_s, 5),
                "phase6i_s": round(i_s, 5),
                "phase6i_transformations": i_structured,
            }
            if ref:
                er, nr = wer(ref, hyp)
                eg, ng = wer(ref, g_res.text)
                ei, ni = wer(ref, i_res.text)
                row["raw_wer_pct"] = round(er / nr * 100, 1) if nr else None
                row["phase6g_wer_pct"] = round(eg / ng * 100, 1) if ng else None
                row["phase6i_wer_pct"] = round(ei / ni * 100, 1) if ni else None
                err_raw += er; w_raw += nr
                err_g += eg; w_g += ng
                err_i += ei; w_i += ni
            rows.append(row)
        except Exception as e:  # noqa: BLE001
            rows.append({"clip": name, "error": f"{type(e).__name__}: {e}"})

    result["clips"] = rows
    if w_raw:
        result["overall_raw_wer_pct"] = round(err_raw / w_raw * 100, 1)
    if w_g:
        result["overall_phase6g_wer_pct"] = round(err_g / w_g * 100, 1)
    if w_i:
        result["overall_phase6i_wer_pct"] = round(err_i / w_i * 100, 1)
    result["status"] = "OK"
    eng.unload()
    return result


def benchmark_phase6h(model_id: str) -> dict:
    """Phase 6H latency/stability benchmark for the one-shot (offline) path.

    The current stack is offline (non-streaming), so there is no "time to first
    partial". This measures the real, user-relevant quantities for the one-shot
    path: per-clip decode time, RTF (= infer_time / audio_duration), final-text
    latency, chunk count, and a determinism/duplicate check obtained by decoding
    the same clip three times and confirming the text is identical (RTF and
    stability are what the Phase 6H objective can honestly report here).

    No transcript text is logged; transcripts are written only to the artifacts
    JSON (a controlled local store), consistent with the existing benchmark.
    References are reused unchanged; F has no reference so no WER is computed.
    """
    result = {"model_id": model_id, "installed": is_model_downloaded(model_id),
              "path": "one-shot-offline"}
    if not result["installed"]:
        result["status"] = "NOT INSTALLED"
        return result

    from sayit.core.transcript_processor import correct_transcript

    clips = _collect_clips()
    eng = TranscriptionEngine(model_name=model_id)
    try:
        t0 = time.perf_counter()
        eng.load_model()
        result["load_s"] = round(time.perf_counter() - t0, 2)
    except Exception as e:  # noqa: BLE001
        result["status"] = f"LOAD FAILED: {type(e).__name__}: {e}"
        return result

    clip_rows = []
    duplicate_count = 0
    for name, path, ref in clips:
        try:
            audio, sr, dur = _read_wav(path)
            # Three repeats to measure determinism / duplicate-rate and a stable
            # median latency.
            texts = []
            times = []
            for _ in range(3):
                s = time.perf_counter()
                hyp = eng.transcribe(audio, sr) or ""
                times.append(time.perf_counter() - s)
                texts.append(hyp)
            median_infer = sorted(times)[1]
            # Determinism: identical input must yield identical output. A
            # mismatch here would be the kind of instability streaming can cause.
            deterministic = len(set(texts)) == 1
            if not deterministic:
                duplicate_count += 1

            cs = time.perf_counter()
            processed = correct_transcript(texts[0]).text
            correction_s = time.perf_counter() - cs

            row = {
                "clip": name,
                "duration_s": round(dur, 2),
                "infer_s_median": round(median_infer, 3),
                "rtf": round(median_infer / dur, 3) if dur else None,
                "time_to_final_s": round(median_infer, 3),  # one-shot: == infer
                "correction_s": round(correction_s, 5),
                "stop_to_final_text_s": round(median_infer + correction_s, 3),
                "chunk_count": eng.last_chunk_count,
                "deterministic_over_3_runs": deterministic,
                "final_char_count": len(processed),
                "raw_transcript": texts[0],
                "processed_transcript": processed,
            }
            if ref:
                err, nwords = wer(ref, texts[0])
                perr, pnwords = wer(ref, processed)
                row["raw_wer_pct"] = round(err / nwords * 100, 1) if nwords else None
                row["processed_wer_pct"] = (
                    round(perr / pnwords * 100, 1) if pnwords else None
                )
            clip_rows.append(row)
        except Exception as e:  # noqa: BLE001
            clip_rows.append({"clip": name, "error": f"{type(e).__name__}: {e}"})

    result["clips"] = clip_rows
    result["clips_measured"] = len(clip_rows)
    result["nondeterministic_clips"] = duplicate_count
    rtfs = [r["rtf"] for r in clip_rows if r.get("rtf") is not None]
    if rtfs:
        result["median_rtf"] = round(sorted(rtfs)[len(rtfs) // 2], 3)
    result["rss_peak_mb"] = _rss_mb()
    result["status"] = "OK"
    eng.unload()
    return result


def main():
    ART.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]

    if args == ["--validate-audio"]:
        print("=== audio validation ===")
        rows = []
        for name, path, _ref in _collect_clips():
            props = audio_properties(path)
            props["clip"] = name
            rows.append(props)
            print(json.dumps(props))
        (ART / "audio-validation.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
        return

    if args and args[0] == "--phase6i":
        rest = args[1:]
        if rest == ["--all"]:
            ids = [m.id for m in AVAILABLE_MODELS]
        else:
            ids = rest or ["sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"]
        for model_id in ids:
            print(f"=== phase6i {model_id} ===")
            res = benchmark_phase6i(model_id)
            out = ART / f"phase6i-{model_id}.json"
            out.write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(
                f"status={res.get('status')} "
                f"raw_wer={res.get('overall_raw_wer_pct')} "
                f"phase6g_wer={res.get('overall_phase6g_wer_pct')} "
                f"phase6i_wer={res.get('overall_phase6i_wer_pct')} -> {out}"
            )
        return

    if args and args[0] == "--phase6h":
        rest = args[1:]
        if rest == ["--all"]:
            ids = [m.id for m in AVAILABLE_MODELS]
        else:
            ids = rest or ["sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"]
        for model_id in ids:
            print(f"=== phase6h {model_id} ===")
            res = benchmark_phase6h(model_id)
            out = ART / f"phase6h-{model_id}.json"
            out.write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(
                f"status={res.get('status')} load_s={res.get('load_s')} "
                f"median_rtf={res.get('median_rtf')} "
                f"nondeterministic={res.get('nondeterministic_clips')} -> {out}"
            )
        return

    if args == ["--all"]:
        ids = [m.id for m in AVAILABLE_MODELS]
    else:
        ids = args or ["sherpa-onnx-whisper-tiny"]

    for model_id in ids:
        print(f"=== {model_id} ===")
        res = benchmark_model(model_id)
        out = ART / f"{model_id}.json"
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"status={res.get('status')} load_s={res.get('load_s')} "
              f"raw_wer={res.get('overall_raw_wer_pct')} "
              f"processed_wer={res.get('overall_processed_wer_pct')} -> {out}")


if __name__ == "__main__":
    main()
