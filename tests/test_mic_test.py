"""Tests for the microphone test primitive (no ASR, no real hardware)."""

from unittest.mock import MagicMock, patch

import numpy as np

from src.sayit.core.audio.mic_test import (
    MicrophoneTestController,
    MicTestResult,
    classify_signal,
)


class TestClassifySignal:
    def test_none_audio_is_no_signal(self):
        assert classify_signal(None) == MicTestResult.NO_SIGNAL

    def test_empty_audio_is_no_signal(self):
        assert classify_signal(np.zeros(0, dtype=np.float32)) == MicTestResult.NO_SIGNAL

    def test_silence_is_no_signal(self):
        quiet = np.full(1000, 0.001, dtype=np.float32)
        assert classify_signal(quiet) == MicTestResult.NO_SIGNAL

    def test_loud_is_signal(self):
        loud = np.full(1000, 0.5, dtype=np.float32)
        assert classify_signal(loud) == MicTestResult.SIGNAL_DETECTED

    def test_peak_override_signal(self):
        assert classify_signal(None, peak=0.9) == MicTestResult.SIGNAL_DETECTED

    def test_peak_override_no_signal(self):
        assert classify_signal(None, peak=0.0) == MicTestResult.NO_SIGNAL

    def test_result_messages_and_success(self):
        assert MicTestResult.SIGNAL_DETECTED.is_success is True
        assert MicTestResult.NO_SIGNAL.is_success is False
        for r in MicTestResult:
            assert isinstance(r.message, str) and r.message


class TestMicrophoneTestController:
    @patch("src.sayit.core.audio.mic_test.AudioRecorder")
    def test_device_unavailable_when_no_devices(self, MockRecorder, qtbot):
        MockRecorder.list_devices.return_value = []
        MockRecorder.return_value = MagicMock()

        ctrl = MicrophoneTestController()
        results = []
        ctrl.finished.connect(results.append)
        ctrl.start()

        assert results == [MicTestResult.DEVICE_UNAVAILABLE]
        assert ctrl.is_running is False

    @patch("src.sayit.core.audio.mic_test.AudioRecorder")
    def test_stream_failed(self, MockRecorder, qtbot):
        MockRecorder.list_devices.return_value = [MagicMock()]
        rec = MockRecorder.return_value
        rec.start.return_value = False
        rec.last_error = "busy"

        ctrl = MicrophoneTestController()
        results = []
        ctrl.finished.connect(results.append)
        ctrl.start()

        assert results == [MicTestResult.STREAM_FAILED]
        assert ctrl.is_running is False

    @patch("src.sayit.core.audio.mic_test.AudioRecorder")
    def test_no_signal_result_and_cleanup(self, MockRecorder, qtbot):
        MockRecorder.list_devices.return_value = [MagicMock()]
        rec = MockRecorder.return_value
        rec.start.return_value = True

        ctrl = MicrophoneTestController(duration_ms=10)
        results = []
        ctrl.finished.connect(results.append)
        ctrl.start()
        assert ctrl.is_running is True

        # No level callbacks fired -> peak stays 0 -> NO_SIGNAL.
        qtbot.waitUntil(lambda: len(results) == 1, timeout=1000)
        assert results == [MicTestResult.NO_SIGNAL]
        # Stream must be released.
        rec.stop.assert_called_once()
        assert ctrl.is_running is False

    @patch("src.sayit.core.audio.mic_test.AudioRecorder")
    def test_signal_detected(self, MockRecorder, qtbot):
        MockRecorder.list_devices.return_value = [MagicMock()]
        rec = MockRecorder.return_value
        rec.start.return_value = True

        ctrl = MicrophoneTestController(duration_ms=10)
        results = []
        ctrl.finished.connect(results.append)
        ctrl.start()

        # Simulate the recorder reporting a strong level during the test.
        ctrl._on_level(0.8)

        qtbot.waitUntil(lambda: len(results) == 1, timeout=1000)
        assert results == [MicTestResult.SIGNAL_DETECTED]
        rec.stop.assert_called_once()

    @patch("src.sayit.core.audio.mic_test.AudioRecorder")
    def test_cancel_releases_stream_without_result(self, MockRecorder, qtbot):
        MockRecorder.list_devices.return_value = [MagicMock()]
        rec = MockRecorder.return_value
        rec.start.return_value = True

        ctrl = MicrophoneTestController(duration_ms=5000)
        results = []
        ctrl.finished.connect(results.append)
        ctrl.start()
        assert ctrl.is_running is True

        ctrl.cancel()
        assert ctrl.is_running is False
        rec.stop.assert_called_once()
        assert results == []  # no result emitted on cancel
