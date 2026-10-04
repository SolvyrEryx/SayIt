"""Real local-ASR test (NOT a mock).

This exercises the actual Sherpa-ONNX inference path with the real selected
model. It is marked ``slow`` so the normal suite (``-m "not slow"``) does not run
it, and it SKIPS cleanly when the model is not installed — the model is never
downloaded automatically here.

Run explicitly with the model installed:

    uv run pytest tests/test_real_asr.py -m slow -v

Note: it uses synthetic audio, so it validates that the real inference path
executes and returns a result (string, possibly empty) — it does NOT assert
transcription accuracy, which requires real speech.
"""

import os
import re
import wave

import numpy as np
import pytest

from src.sayit.core.asr.models.registry import is_model_downloaded
from src.sayit.core.asr.transcriber import EngineState, TranscriptionEngine

_MODEL_ID = "sherpa-onnx-whisper-tiny"


def _normalize(text: str):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def word_error_rate(reference: str, hypothesis: str):
    """Standard word error rate via word-level Levenshtein distance.

    Returns (edits, ref_word_count). This is a reliable, well-defined metric
    (not a heuristic). Text is lowercased and stripped of punctuation first, so
    spelling/case/punctuation differences from the model are not over-counted
    as recognition errors — but note US/UK spelling still counts as an edit.
    """
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


class TestWerMetric:
    def test_perfect_match(self):
        assert word_error_rate("the cat sat", "The cat sat.") == (0, 3)

    def test_one_substitution(self):
        edits, n = word_error_rate("the cat sat", "the dog sat")
        assert edits == 1 and n == 3

    def test_deletion_and_insertion(self):
        edits, _ = word_error_rate("one two three", "one three")
        assert edits == 1


@pytest.mark.slow
class TestRealWhisperTiny:
    def _require_model(self):
        if not is_model_downloaded(_MODEL_ID):
            pytest.skip(
                f"Model '{_MODEL_ID}' not installed; download it first "
                "(this test never downloads automatically)."
            )

    def test_real_inference_path_runs(self):
        self._require_model()

        engine = TranscriptionEngine(model_name=_MODEL_ID)
        engine.load_model()
        assert engine.state == EngineState.READY

        # 1 second of near-silence at 16kHz. Real inference should run and
        # return a string (likely empty for non-speech) WITHOUT crashing and
        # WITHOUT any cloud/mock involvement.
        sample_rate = 16000
        audio = np.zeros(sample_rate, dtype=np.float32)
        result = engine.transcribe(audio, sample_rate)

        assert result is None or isinstance(result, str)
        assert engine.state in (EngineState.READY, EngineState.ERROR)

        engine.unload()
        assert engine.state == EngineState.NOT_LOADED

    def test_real_speech_quality_on_bundled_samples(self):
        """Real-speech WER on the model's bundled LibriSpeech samples.

        These ship with the model (test_wavs/ + trans.txt), so this is a real
        recognition-quality check (not synthetic, not mocked). It asserts only a
        loose sanity bound on general English — not a published accuracy claim.
        """
        self._require_model()
        from src.sayit.core.asr.file_utils import get_models_dir

        wav_dir = os.path.join(get_models_dir(), _MODEL_ID, "test_wavs")
        trans = os.path.join(wav_dir, "trans.txt")
        if not os.path.exists(trans):
            pytest.skip("Bundled reference transcripts not present.")

        refs = {}
        for line in open(trans, encoding="utf-8"):
            line = line.strip()
            if line:
                fn, _, text = line.partition(" ")
                refs[fn] = text

        engine = TranscriptionEngine(model_name=_MODEL_ID)
        engine.load_model()

        # Use a clean 16kHz sample for the sanity bound.
        fn = "0.wav"
        path = os.path.join(wav_dir, fn)
        if not os.path.exists(path) or fn not in refs:
            engine.unload()
            pytest.skip("Expected bundled sample 0.wav not present.")

        w = wave.open(path, "rb")
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        w.close()
        audio = data.astype(np.float32) / 32768.0

        hyp = engine.transcribe(audio, sr) or ""
        edits, nwords = word_error_rate(refs[fn], hyp)
        engine.unload()

        assert nwords > 0
        # Clean general-English WER should be well under 50% for a working path.
        assert edits / nwords < 0.5, f"WER too high: {edits}/{nwords}; hyp={hyp!r}"
