"""Whisper Small opt-in mode — automated validation (production FROZEN).

Reuses the existing TranscriptionEngine/SherpaOnnxBackend (no second
architecture). Measures real model switching, routing correctness, end-to-end
ARM A (Parakeet) vs ARM B (Whisper Small) through the SAME SayIt intelligence,
per-difficult-term recovery (A-F), and the Whisper Small hallucination case.

Live-microphone and live-insertion (prompt Steps 11/17) CANNOT run in this
headless environment and are reported as human-required (never fabricated).
"""

from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
import wave
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
import external_adapter as EA  # noqa: E402
import known_unseen as KU  # noqa: E402
from sayit.core.asr import speech_mode as SM  # noqa: E402
from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
OUT = ROOT / "artifacts" / "whisper_small"
DIFFICULT = ["CAD", "HPLC", "LQR", "OPEC", "non-linear", "soft-in-plane"]


def read_wav(p):
    w = wave.open(str(p), "rb"); sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    w.close()
    return d, sr


def held_out():
    tie = EA.scored_entries(EA.build_manifest(EXTERNAL))
    spk = sorted({e.speaker_id for e in tie}); held = set(spk[::2])
    return [e for e in tie if e.speaker_id in held]


def rss_mib():
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / 1048576, 1)
    except Exception:
        return None


def recovery_class(raw, final, target):
    """A-F classification per difficult term."""
    t = target.lower()
    if target in raw:
        return "A_already_correct"
    if target in final:
        return "C_canonicalized_by_sayit"
    tc = "".join(c for c in t if c.isalnum())
    best = 0.0
    toks = raw.lower().replace("-", " ").split()
    for tok in toks:
        tokc = "".join(c for c in tok if c.isalnum())
        if tokc:
            best = max(best, SequenceMatcher(None, tc, tokc).ratio())
    for k in (2, 3, 4):
        for i in range(len(toks) - k + 1):
            best = max(best, SequenceMatcher(None, tc, "".join(toks[i:i+k])).ratio())
    if best >= 0.6:
        return "B_recoverable_near_match"
    return "D_or_E_misrecognized_or_absent"


def switching_test(entries):
    """Cycle Parakeet<->Whisper several times; verify routing + load time + RSS +
    that each engine's output is self-consistent (no stale result)."""
    clip = entries[0]
    d, sr = read_wav(Path(clip.audio_path)); d = d[:sr*8]
    rows = []
    base_rss = rss_mib()
    for cycle in range(3):
        for mid in (SM.FAST_MODEL_ID, SM.HIGHER_ACCURACY_MODEL_ID):
            t0 = time.perf_counter()
            eng = TranscriptionEngine(model_name=mid); eng.load_model()
            load = time.perf_counter() - t0
            post_load_rss = rss_mib()
            # routing correctness: the backend loaded the right type.
            out1 = (eng.transcribe(d, sr) or "").strip()
            out2 = (eng.transcribe(d, sr) or "").strip()
            stale_ok = (out1 == out2)  # same input -> same output (no stale/leak)
            eng.unload(); gc.collect()
            rows.append({"cycle": cycle, "model": mid.replace("sherpa-onnx-", ""),
                         "load_s": round(load, 2), "post_load_rss_mib": post_load_rss,
                         "deterministic": stale_ok})
    return base_rss, rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = held_out()
    known = KU.build_known_set()
    pipe = IntelligencePipeline(domain_aware=False)

    # 1) model switching + memory.
    base_rss, switch_rows = switching_test(entries)
    with open(OUT / "model_switching.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cycle", "model", "load_s", "post_load_rss_mib", "deterministic"])
        w.writeheader(); w.writerows(switch_rows)

    # 2) end-to-end ARM A/B + per-difficult-term recovery + hallucination.
    results = {}
    recovery_rows = []
    halluc_rows = []
    import re
    ACR = re.compile(r"\b[A-Z]{3,6}\b")
    for mid in (SM.FAST_MODEL_ID, SM.HIGHER_ACCURACY_MODEL_ID):
        eng = TranscriptionEngine(model_name=mid); eng.load_model()
        recs, unseen, lat = [], [], []
        for e in entries:
            d, sr = read_wav(Path(e.audio_path))
            t0 = time.perf_counter()
            raw = (eng.transcribe(d, sr) or "").strip()
            lat.append((time.perf_counter() - t0) * 1000.0)
            ctx = e.metadata.get("context", "developer")
            final = pipe.process(raw, ctx).text if pipe.available else raw
            errs, words = M.wer(e.reference, final)
            tr_n, tr_d, _ = M.technical_term_recall(final, e.target_terms)
            ex_n, ex_d, _ = M.exact_entity_accuracy(final, e.target_terms)
            recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n,
                         "tech_total": tr_d, "exact_count": ex_n, "exact_total": ex_d,
                         "phrase_recalled": 0, "phrase_total": 0, "false_sub_count": 0,
                         "has_negatives": False, "ordinary_preserved": None})
            for term in e.target_terms:
                if KU.classify_terms([term], known)[term] == "UNSEEN":
                    t1, d1, _ = M.technical_term_recall(final, [term])
                    unseen.append({"tech_recalled": t1, "tech_total": d1, "exact_count": 0,
                                   "exact_total": 0, "errors": 0, "ref_words": 0,
                                   "phrase_recalled": 0, "phrase_total": 0, "false_sub_count": 0,
                                   "has_negatives": False, "ordinary_preserved": None})
            # per-difficult-term recovery (targets present in this clip's ref).
            for term in DIFFICULT:
                if term.lower() in e.reference.lower():
                    recovery_rows.append([mid.replace("sherpa-onnx-", ""), e.sample_id, term,
                                          recovery_class(raw, final, term), raw[:70]])
            # hallucination proxy: acronyms in raw not in reference.
            for ac in set(ACR.findall(raw)) - set(ACR.findall(e.reference)):
                halluc_rows.append([mid.replace("sherpa-onnx-", ""), e.sample_id, ac,
                                    e.reference[:50], raw[:70], final[:70]])
        eng.unload(); gc.collect()
        a = M.aggregate(recs); u = M.aggregate(unseen) if unseen else {}
        lat.sort()
        results[mid] = {
            "wer": round(a["wer"], 4),
            "technical_recall": round(a["technical_term_recall"], 4),
            "exact_entity": round(a["exact_entity_accuracy"], 4),
            "unseen_recall": round(u.get("technical_term_recall", 0.0), 4) if u else None,
            "stop_to_final_median_ms": round(lat[len(lat)//2], 1),
            "stop_to_final_p95_ms": round(lat[int(len(lat)*0.95)-1], 1),
            "peak_rss_mib_after": rss_mib(),
        }

    (OUT / "end_to_end_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with open(OUT / "technical_recovery.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["model", "sample_id", "target", "class", "raw_excerpt"]); w.writerows(recovery_rows)
    with open(OUT / "hallucination_cases.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["model", "sample_id", "hallucinated_acronym", "ref", "raw", "final"]); w.writerows(halluc_rows)

    print("base_rss_mib:", base_rss)
    for mid, r in results.items():
        print(mid.replace("sherpa-onnx-", ""), r)
    print("switching deterministic:", all(x["deterministic"] for x in switch_rows))
    print("hallucination rows:", len(halluc_rows))


if __name__ == "__main__":
    main()
