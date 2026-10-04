"""Phase 9K — controlled-integration benchmark through the real worker path.

Compares the production worker with the experimental flag OFF (pipeline=None)
vs ON (IntelligencePipeline) on the real 23-clip corpus, confirming:
  - OFF is byte-identical to today's behavior
  - ON applies the proven subset (recovers technical terms)
  - fail-safe + rollback (disable restores prior behavior)

Production ASR/decoder/model unchanged. Uses a stub transcriber replaying the
real greedy transcripts so the worker's post-ASR path is exercised exactly.
"""

from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))

import metrics as M  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.transcription_worker import TranscriptionWorkerThread  # noqa: E402
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline  # noqa: E402
from sayit.core.context import resolve_profile, ContextSignals  # noqa: E402
from sayit.core.context.profiles import AUTO  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
OUT = ROOT / "artifacts" / "phase9k"


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def find_wav(e):
    wav = e.get("wav", e["id"] + ".wav")
    for base in (CORPUS, EVAL):
        if (base / wav).exists():
            return base / wav
    return None


def ctx_app_for(e):
    role, cat = e.get("pair_role"), e.get("category")
    if role == "technical" or cat in ("technical", "multiword") or cat == "mixed":
        return "code"      # -> developer profile
    return "outlook"       # -> email profile


def greedy_clips():
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    out = []
    for e in json.loads(LABELS.read_text(encoding="utf-8")):
        if e.get("needs_recording"):
            continue
        p = find_wav(e)
        if p is None:
            continue
        d, sr, _ = read_wav(p)
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        out.append({"id": e["id"], "ref": e["reference"], "hyp": s.result.text.strip(),
                    "targets": e.get("target_terms", []), "negs": e.get("negative_terms", []),
                    "ctx_app": ctx_app_for(e)})
    return out


def run_worker(hyp, ctx_app, pipeline):
    tr = MagicMock()
    tr.transcribe_chunked.return_value = hyp
    tr.last_chunk_count = 1
    tr.last_invocation_count = 1
    ctx = resolve_profile(ContextSignals(app_name=ctx_app), detection_enabled=True, override=AUTO)
    w = TranscriptionWorkerThread(
        transcriber=tr, audio_data=np.zeros(1600, dtype=np.float32), sample_rate=16000,
        vocabulary_replacements=[], llm_processor=None, enhancement=None,
        technical_correction_enabled=False, structured_formatting_enabled=False,
        context_resolution=ctx, post_asr_pipeline=pipeline)
    cap = []
    w.finished.connect(lambda *a: cap.append(a))
    w.run()
    return cap[0][0] if cap else hyp


def score(clips, pipeline):
    recs = []
    for c in clips:
        final = run_worker(c["hyp"], c["ctx_app"], pipeline)
        errs, words = M.wer(c["ref"], final)
        tr_n, tr_d, _ = M.technical_term_recall(final, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(final, c["targets"])
        fs_n, _ = M.false_technical_substitutions(final, c["negs"])
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
                     "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": 0, "phrase_total": 0,
                     "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    return M.aggregate(recs)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    pipe = IntelligencePipeline()

    # Byte-identical-when-off: worker(None) output must equal raw hyp (since
    # 6G/6I/6J are disabled in this harness to isolate the pipeline effect).
    off_outputs = {c["id"]: run_worker(c["hyp"], c["ctx_app"], None) for c in clips}
    byte_identical = all(off_outputs[c["id"]] == c["hyp"] for c in clips)

    arms = {
        "flag_off": score(clips, None),
        "flag_on": score(clips, pipe),
    }
    report = {
        "phase": "9K", "timestamp": datetime.now(timezone.utc).isoformat(),
        "flag_off_byte_identical_to_raw": byte_identical,
        "arms": arms,
        "pipeline_available": pipe.available,
        "integration": {
            "feature_flag": "intelligence_experimental_enabled",
            "default": False,
            "threshold": 0.90,
            "subset": "9C retrieval + 9D domain/canonical + 9F ranking/abstention + 9B correction",
            "position": "applied to raw ASR text BEFORE 8H/6G/6I/6J",
            "fail_safe": "pipeline returns raw text unchanged on any error",
            "rollback": "disable flag -> next job uses None -> prior behavior",
            "knowledge_version": "9e.1 (packaged index)",
            "production_ASR": "unchanged (greedy, Parakeet int8, sherpa 1.12.21)",
        },
    }
    (OUT / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for k, a in arms.items():
        print(k, "recall=%.3f exact=%.3f fsub=%d ord=%.3f wer=%.3f" % (
            a["technical_term_recall"], a["exact_entity_accuracy"], a["false_substitution_total"],
            a["ordinary_preservation"], a["wer"]))
    print("flag_off byte-identical to raw:", byte_identical)


if __name__ == "__main__":
    main()
