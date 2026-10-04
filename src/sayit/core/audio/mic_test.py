"""Microphone test primitive.

Provides a short, ASR-free check of whether a usable microphone signal is being
received. It reuses :class:`AudioRecorder` so there is a single audio-capture
code path, and keeps all test state local — it does not touch the application's
dictation AppState, never creates a transcription job, and always releases the
stream when the test ends.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from ...utils.logger import get_logger
from .recorder import AudioRecorder

logger = get_logger(__name__)


# Peak amplitude (0.0-1.0, float32) below which captured audio is treated as
# silence / no usable input. Chosen conservatively above typical noise floors
# so a truly silent/absent mic is distinguished from real speech or ambient
# sound. This is a heuristic, not a calibrated measurement.
_SIGNAL_PEAK_THRESHOLD = 0.01


class MicTestResult(Enum):
    DEVICE_UNAVAILABLE = auto()  # No input device / device could not be selected
    STREAM_FAILED = auto()  # Stream could not be started
    NO_SIGNAL = auto()  # Stream opened but no meaningful signal captured
    SIGNAL_DETECTED = auto()  # Usable input detected

    @property
    def is_success(self) -> bool:
        return self is MicTestResult.SIGNAL_DETECTED

    @property
    def message(self) -> str:
        return {
            MicTestResult.DEVICE_UNAVAILABLE: "No microphone was found.",
            MicTestResult.STREAM_FAILED: "The microphone could not be started.",
            MicTestResult.NO_SIGNAL: (
                "No sound was detected. Check that the right microphone is "
                "selected and that it is not muted."
            ),
            MicTestResult.SIGNAL_DETECTED: "Microphone is picking up sound.",
        }[self]


def classify_signal(audio: Optional[np.ndarray], peak: Optional[float] = None) -> MicTestResult:
    """Classify captured test audio as signal vs. no-signal.

    ``peak`` may be provided directly (already-computed level); otherwise it is
    derived from ``audio``. Pure and deterministic for unit testing.
    """
    if peak is None:
        if audio is None or len(audio) == 0:
            return MicTestResult.NO_SIGNAL
        data = audio.astype(np.float32)
        if data.dtype == np.int16:  # defensive; astype already handled
            data = data / 32768.0
        peak = float(np.max(np.abs(data))) if data.size else 0.0

    if peak >= _SIGNAL_PEAK_THRESHOLD:
        return MicTestResult.SIGNAL_DETECTED
    return MicTestResult.NO_SIGNAL


class MicrophoneTestController(QObject):
    """Runs a short microphone test and reports the outcome once.

    Signals:
        level: Emitted periodically with the current input level (0.0-1.0) so a
               simple meter can be shown during the test.
        finished: Emitted once with a :class:`MicTestResult` when the test ends.
    """

    level = Signal(float)
    finished = Signal(object)  # MicTestResult

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[str] = None,
        duration_ms: int = 1500,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._duration_ms = duration_ms
        self._peak = 0.0
        self._running = False
        self._recorder = AudioRecorder(
            sample_rate=sample_rate,
            device=device,
            on_audio_level=self._on_level,
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._finish)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Begin a short test. Emits ``finished`` exactly once per start."""
        if self._running:
            return

        # No usable input device selected/available.
        try:
            devices = AudioRecorder.list_devices()
        except Exception as e:
            logger.error(f"Could not enumerate input devices: {e}")
            self.finished.emit(MicTestResult.DEVICE_UNAVAILABLE)
            return

        if not devices:
            self.finished.emit(MicTestResult.DEVICE_UNAVAILABLE)
            return

        self._peak = 0.0
        if not self._recorder.start():
            logger.warning(
                f"Mic test could not start stream: {self._recorder.last_error}"
            )
            self.finished.emit(MicTestResult.STREAM_FAILED)
            return

        self._running = True
        self._timer.start(self._duration_ms)

    def _on_level(self, level: float) -> None:
        # AudioRecorder already normalizes level roughly to 0..1; track the peak.
        self._peak = max(self._peak, float(level))
        self.level.emit(float(level))

    def _finish(self) -> None:
        if not self._running:
            return
        self._running = False
        # Always release the microphone, regardless of outcome.
        try:
            self._recorder.stop()
        except Exception as e:
            logger.error(f"Error stopping mic test recorder: {e}")

        result = classify_signal(None, peak=self._peak)
        logger.info(f"Mic test result: {result.name} (peak={self._peak:.4f})")
        self.finished.emit(result)

    def cancel(self) -> None:
        """Abort the test and release resources without emitting a result."""
        self._timer.stop()
        if self._running:
            self._running = False
            try:
                self._recorder.stop()
            except Exception as e:
                logger.error(f"Error stopping mic test recorder on cancel: {e}")
