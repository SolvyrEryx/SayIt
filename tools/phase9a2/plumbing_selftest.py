"""Phase 9A.2R — plumbing-only self-test for the record -> ingest -> rerun loop.

This proves the ingest/auto-detect machinery works the moment VALID audio
appears, WITHOUT fabricating speech and WITHOUT scoring synthetic audio for
accuracy. It:

  1. creates a throwaway temp corpus + temp labels (two entries flagged
     needs_recording) in a TemporaryDirectory,
  2. writes placeholder WAVs — pure SILENCE at the correct capture spec
     (mono/16000/16-bit) — which exist ONLY to exercise file detection and
     spec validation (they are never transcribed or scored here),
  3. runs the ingest status build + apply-update logic against the temp copy,
  4. asserts the loop flips needs_recording -> false and reports
     recording_complete,
  5. the TemporaryDirectory is auto-deleted on exit.

Run directly:  uv run python tools/phase9a2/plumbing_selftest.py
(Also exercised by tests/test_contextual_biasing_phase9a2r.py.)
"""

from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_status as ING  # noqa: E402


def write_silence_wav(path: Path, seconds: float = 0.4, sr: int = 16000):
    """Write a spec-correct (mono/16k/16-bit) SILENCE wav. Plumbing placeholder
    only — NOT speech, never scored for accuracy."""
    frames = int(seconds * sr)
    data = np.zeros(frames, dtype=np.int16)
    w = wave.open(str(path), "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(data.tobytes())
    w.close()


def run_selftest() -> dict:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        corpus = tmp / "corpus"
        corpus.mkdir()
        labels_path = tmp / "labels.json"

        entries = [
            {"id": "TMP_OK", "wav": "TMP_OK.wav", "reference": "placeholder",
             "target_terms": [], "negative_terms": [], "category": "ordinary",
             "synthetic": True, "needs_recording": True},
            {"id": "TMP_MISSING", "wav": "TMP_MISSING.wav", "reference": "placeholder",
             "target_terms": [], "negative_terms": [], "category": "ordinary",
             "synthetic": True, "needs_recording": True},
            {"id": "TMP_BADSPEC", "wav": "TMP_BADSPEC.wav", "reference": "placeholder",
             "target_terms": [], "negative_terms": [], "category": "ordinary",
             "synthetic": True, "needs_recording": True},
        ]
        labels_path.write_text(json.dumps(entries), encoding="utf-8")

        # TMP_OK: valid spec. TMP_BADSPEC: wrong sample rate. TMP_MISSING: absent.
        write_silence_wav(corpus / "TMP_OK.wav", sr=16000)
        write_silence_wav(corpus / "TMP_BADSPEC.wav", sr=8000)

        # Point the ingest module's path constants at the temp fixture.
        orig_labels, orig_corpus, orig_eval = ING.LABELS, ING.CORPUS, ING.EVAL
        try:
            ING.LABELS, ING.CORPUS, ING.EVAL = labels_path, corpus, corpus
            status_before = ING.build_status(entries)
            n_updated = ING.apply_updates(entries, status_before)
            status_after = ING.build_status(entries)
        finally:
            ING.LABELS, ING.CORPUS, ING.EVAL = orig_labels, orig_corpus, orig_eval

        return {
            "present_before": status_before["audio_present"],   # TMP_OK + TMP_BADSPEC = 2
            "valid_before": status_before["valid_spec"],         # TMP_OK only = 1
            "invalid_before": status_before["invalid_spec"],     # TMP_BADSPEC = 1
            "missing_before": status_before["missing"],          # TMP_MISSING = 1
            "updated": n_updated,                                 # only TMP_OK flips = 1
            "tmp_ok_still_blocking": "TMP_OK" in status_after["blocking_ids"],      # False
            "tmp_badspec_blocking": "TMP_BADSPEC" in status_after["blocking_ids"],  # True
            "tmp_missing_blocking": "TMP_MISSING" in status_after["blocking_ids"],  # True
        }


if __name__ == "__main__":
    r = run_selftest()
    print(json.dumps(r, indent=2))
    assert r["valid_before"] == 1 and r["invalid_before"] == 1 and r["missing_before"] == 1
    assert r["updated"] == 1
    assert r["tmp_ok_still_blocking"] is False
    assert r["tmp_badspec_blocking"] is True and r["tmp_missing_blocking"] is True
    print("PLUMBING SELF-TEST PASSED")
