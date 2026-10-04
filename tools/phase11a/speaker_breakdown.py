"""Phase 11A — per-speaker metric breakdown on the staged external data."""

from __future__ import annotations

import csv
import json
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
import external_adapter as EA  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
EXTERNAL = ROOT / "artifacts" / "phase10" / "external"
OUT = ROOT / "artifacts" / "phase10"


def read_wav(p):
    w = wave.open(str(p), "rb"); sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    w.close()
    return d, sr


def main():
    entries = EA.scored_entries(EA.build_manifest(EXTERNAL))
    if not entries:
        print("no external data staged")
        return
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    pipe = IntelligencePipeline()

    per_sp = defaultdict(lambda: {"clips": 0, "errA": 0, "errB": 0, "words": 0,
                                  "changed": 0})
    for e in entries:
        d, sr = read_wav(Path(e.audio_path))
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        raw = s.result.text.strip()
        corr = pipe.process(raw, "developer").text if pipe.available else raw
        ea, w = M.wer(e.reference, raw)
        eb, _ = M.wer(e.reference, corr)
        sp = per_sp[e.speaker_id]
        sp["clips"] += 1; sp["errA"] += ea; sp["errB"] += eb; sp["words"] += w
        sp["changed"] += 1 if corr != raw else 0

    # Aggregate + per-speaker WER; count speakers where B is worse than A.
    worse = 0
    with open(OUT / "speaker_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["speaker_id", "clips", "wer_rawA", "wer_expB", "changed_clips"])
        for sp in sorted(per_sp):
            m = per_sp[sp]
            wa = m["errA"] / m["words"] if m["words"] else 0
            wb = m["errB"] / m["words"] if m["words"] else 0
            if wb > wa + 1e-9:
                worse += 1
            w.writerow([sp, m["clips"], round(wa, 4), round(wb, 4), m["changed"]])
    print(f"speakers={len(per_sp)} | speakers_where_B_worse_than_A={worse}")


if __name__ == "__main__":
    main()
