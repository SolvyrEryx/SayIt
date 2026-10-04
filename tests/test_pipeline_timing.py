"""Phase 6H tests: pipeline timing, duplicate prevention, chunk accounting, and
the streaming-capability finding.

The current engine is an offline (non-streaming) Sherpa-ONNX recognizer. These
tests verify the Phase 6H instrumentation and the duplicate-prevention
guarantees without claiming streaming behavior that does not exist. The one-shot
"exactly once" and seam de-duplication tests are explicit regression guards
against the classic streaming failure mode (text inserted more than once).
"""

from unittest.mock import MagicMock

import numpy as np

from src.sayit.core.asr.pipeline_timing import PipelineTiming
from src.sayit.core.asr.transcription_worker import TranscriptionWorkerThread
from src.sayit.core.audio.audio_processor import AudioProcessor


class TestPipelineTiming:
    def test_derived_latencies(self):
        t = PipelineTiming(job_id=1)
        t.mark("recording_start", 0.0)
        t.mark("recording_stop", 2.0)
        t.mark("asr_start", 2.0)
        t.mark("asr_final", 2.5)
        t.mark("correction_start", 2.5)
        t.mark("correction_end", 2.503)
        t.mark("insertion_start", 2.503)
        t.mark("insertion_end", 2.51)

        assert t.recording_duration == 2.0
        assert t.time_to_final_transcript == 0.5
        assert abs(t.correction_overhead - 0.003) < 1e-9
        assert abs(t.stop_to_final_text - 0.503) < 1e-9
        assert abs(t.end_to_end - 2.51) < 1e-9

    def test_missing_stages_are_none(self):
        t = PipelineTiming(job_id=2)
        assert t.time_to_final_transcript is None
        assert t.end_to_end is None

    def test_first_partial_offline_is_none(self):
        # The offline path never produces a partial, so time_to_first_partial
        # must be None and the summary must say so (not fake a streaming value).
        t = PipelineTiming(job_id=3)
        t.mark("asr_start", 1.0)
        t.mark("asr_final", 1.4)
        assert t.first_partial is None
        assert t.time_to_first_partial is None
        assert "n/a(offline)" in t.summary()

    def test_summary_contains_no_transcript_text(self):
        # The summary must only contain timing/counters, never transcript text.
        t = PipelineTiming(job_id=4)
        t.mark("recording_start", 0.0)
        t.mark("recording_stop", 1.0)
        t.mark("asr_start", 1.0)
        t.mark("asr_final", 1.3)
        t.final_char_count = 42
        s = t.summary()
        assert "job 4" in s
        assert "chars=42" in s
        # No lowercase sentence content; only tokens we expect.
        assert "GitHub" not in s

    def test_unknown_stage_goes_to_extra(self):
        t = PipelineTiming(job_id=5)
        t.mark("not_a_real_stage", 9.0)
        assert t.extra["not_a_real_stage"] == 9.0


class TestSeamDeduplication:
    def setup_method(self):
        self.p = AudioProcessor()

    def test_exact_word_overlap_removed(self):
        # Classic overlap artifact: chunk 2 repeats the tail of chunk 1.
        out = self.p.combine_transcriptions(
            ["push the code to GitHub", "to GitHub then run the script"]
        )
        assert out == "push the code to GitHub then run the script"

    def test_single_word_overlap_removed(self):
        out = self.p.combine_transcriptions(["hello world", "world again"])
        assert out == "hello world again"

    def test_no_false_dedupe_on_distinct_text(self):
        out = self.p.combine_transcriptions(
            ["the first part", "a second part entirely"]
        )
        assert out == "the first part a second part entirely"

    def test_case_insensitive_overlap(self):
        out = self.p.combine_transcriptions(["ending WITH github", "GitHub continues"])
        assert out == "ending WITH github continues"

    def test_full_duplicate_chunk_collapses(self):
        # If a chunk is entirely a repeat of the previous tail, it collapses to
        # nothing extra (no "X X" duplication).
        out = self.p.combine_transcriptions(["push the code", "push the code"])
        assert out == "push the code"

    def test_empty_and_whitespace_handling(self):
        assert self.p.combine_transcriptions([]) == ""
        assert self.p.combine_transcriptions(["", "   "]) == ""
        assert self.p.combine_transcriptions(["only"]) == "only"


class TestChunkAccounting:
    def test_one_shot_sets_chunk_count_one(self, monkeypatch):
        from src.sayit.core.asr import transcriber as tr

        eng = tr.TranscriptionEngine()
        # Short audio -> no chunking.
        monkeypatch.setattr(tr, "needs_chunking", lambda a, sr: False)
        eng.transcribe = MagicMock(return_value="hello")
        out = eng.transcribe_chunked(np.zeros(1600, dtype=np.float32), 16000)
        assert out == "hello"
        assert eng.last_chunk_count == 1
        assert eng.transcribe.call_count == 1

    def test_chunked_sets_chunk_count(self, monkeypatch):
        from src.sayit.core.asr import transcriber as tr

        eng = tr.TranscriptionEngine()
        monkeypatch.setattr(tr, "needs_chunking", lambda a, sr: True)
        eng._audio_processor = MagicMock()
        eng._audio_processor.split_audio.return_value = [MagicMock(), MagicMock(), MagicMock()]
        eng._audio_processor.combine_transcriptions.return_value = "a b c"
        eng.transcribe = MagicMock(side_effect=["a", "b", "c"])
        out = eng.transcribe_chunked(MagicMock(), 16000)
        assert out == "a b c"
        assert eng.last_chunk_count == 3


class TestWorkerTimingAndExactlyOnce:
    def _worker(self, timing, transcribe_return="push the code to GitHub"):
        transcriber = MagicMock()
        transcriber.transcribe_chunked.return_value = transcribe_return
        transcriber.last_chunk_count = 1
        transcriber.last_invocation_count = 1
        return TranscriptionWorkerThread(
            transcriber=transcriber,
            audio_data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            vocabulary_replacements=[],
            llm_processor=None,
            enhancement=None,
            timing=timing,
        )

    def test_worker_marks_timing_and_counts(self, qtbot):
        timing = PipelineTiming(job_id=10)
        timing.mark("recording_start", 0.0)
        timing.mark("recording_stop", 1.0)
        worker = self._worker(timing)

        finished = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()

        assert len(finished) == 1  # exactly one finished emission
        assert timing.asr_start is not None
        assert timing.asr_final is not None
        assert timing.chunk_count == 1
        assert timing.asr_invocations == 1

    def test_single_finished_emission_exactly_once(self, qtbot):
        # Regression guard: one utterance -> exactly one finished signal, so the
        # app inserts exactly once (no duplicate insertion).
        worker = self._worker(None)
        finished = []
        errors = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.error.connect(lambda m: errors.append(m))
        worker.run()
        assert len(finished) == 1
        assert errors == []
        final_text = finished[0][0]
        # The final text must be the single corrected transcript, not a doubled
        # string like "...GitHub ...GitHub".
        assert final_text.count("GitHub") == 1

    def test_correction_disabled_still_marks_boundary(self, qtbot):
        timing = PipelineTiming(job_id=11)
        worker = TranscriptionWorkerThread(
            transcriber=self._worker(None)._transcriber,
            audio_data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            vocabulary_replacements=[],
            llm_processor=None,
            enhancement=None,
            technical_correction_enabled=False,
            structured_formatting_enabled=False,
            timing=timing,
        )
        worker.run()
        assert timing.correction_start is not None
        assert timing.correction_end is not None
        assert timing.correction_overhead == 0.0
