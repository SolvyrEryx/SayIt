from unittest.mock import MagicMock, patch

import pytest

from src.sayit.core.asr.transcriber import EngineState, TranscriptionEngine


class TestEngineState:
    def test_initial_state_not_loaded(self):
        engine = TranscriptionEngine(model_name="test/model")
        assert engine.state == EngineState.NOT_LOADED

    def test_is_ready_false_initially(self):
        engine = TranscriptionEngine(model_name="test/model")
        assert engine.is_ready is False


class TestEngineCallbacks:
    def test_state_change_callback(self):
        states = []

        def on_state(state, msg):
            states.append((state, msg))

        engine = TranscriptionEngine(model_name="test/model", on_state_change=on_state)

        engine._set_state(EngineState.LOADING, "Loading model...")

        assert len(states) == 1
        assert states[0][0] == EngineState.LOADING
        assert states[0][1] == "Loading model..."


class TestEngineConfiguration:
    def test_model_name_stored(self):
        engine = TranscriptionEngine(
            model_name="sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
        )
        assert engine.model_name == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"

    def test_backend_name_is_sherpa_onnx(self):
        engine = TranscriptionEngine(model_name="nvidia/parakeet-tdt-0.6b-v3")
        assert engine.backend_name == "SHERPA_ONNX"


class TestEngineUnload:
    def test_unload_without_load(self):
        engine = TranscriptionEngine(model_name="test/model")
        engine.unload()
        assert engine.state == EngineState.NOT_LOADED


class TestTranscribeChunked:
    @patch("src.sayit.core.asr.transcriber.needs_chunking")
    def test_transcribe_chunked_orchestration(self, mock_needs_chunking):
        mock_needs_chunking.return_value = True

        engine = TranscriptionEngine()
        engine._audio_processor = MagicMock()

        chunk1 = MagicMock()
        chunk2 = MagicMock()
        engine._audio_processor.split_audio.return_value = [chunk1, chunk2]

        engine.transcribe = MagicMock(side_effect=["Part1", "Part2"])

        engine._audio_processor.combine_transcriptions.return_value = "Part1 Part2"

        result = engine.transcribe_chunked(MagicMock(), 16000)

        assert result == "Part1 Part2"
        assert engine.transcribe.call_count == 2
        engine._audio_processor.split_audio.assert_called_once()
        engine._audio_processor.combine_transcriptions.assert_called_once_with(
            ["Part1", "Part2"]
        )


@pytest.mark.slow
class TestEngineIntegration:
    def test_load_real_model(self):
        pytest.skip("Requires ~1GB model download - run manually")


class TestWorkerCancellation:
    def test_cancel_before_start_emits_cancelled(self, qtbot):
        import numpy as np

        from src.sayit.core.asr.transcription_worker import (
            TranscriptionWorkerThread,
        )

        transcriber = MagicMock()
        worker = TranscriptionWorkerThread(
            transcriber=transcriber,
            audio_data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            vocabulary_replacements=[],
            llm_processor=None,
            enhancement=None,
        )

        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        worker.cancel()
        assert worker.is_cancelled is True

        # Run synchronously (not via start()) to assert the cooperative check.
        worker.run()

        # Cancelled before start: ASR must not be invoked and an error/"Cancelled"
        # signal is emitted so the owner can resolve state.
        transcriber.transcribe_chunked.assert_not_called()
        assert errors == ["Cancelled"]

    def test_cancel_after_transcription_discards_result(self, qtbot):
        import numpy as np

        from src.sayit.core.asr.transcription_worker import (
            TranscriptionWorkerThread,
        )

        transcriber = MagicMock()
        transcriber.transcribe_chunked.return_value = "hello world"
        worker = TranscriptionWorkerThread(
            transcriber=transcriber,
            audio_data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            vocabulary_replacements=[],
            llm_processor=None,
            enhancement=None,
        )

        finished = []
        errors = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.error.connect(lambda msg: errors.append(msg))

        # Simulate cancellation that lands after ASR returns: set the flag, then
        # run. The result must be discarded (no finished emission).
        worker.cancel()
        worker.run()

        assert finished == []
        assert errors == ["Cancelled"]
