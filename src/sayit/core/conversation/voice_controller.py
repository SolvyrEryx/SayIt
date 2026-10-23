"""Voice-to-chat controller for the conversational assistant.

Drives a chat-specific recording session that REUSES SayIt's existing audio
recorder and local ASR engine (no second speech engine) but is strictly
isolated from the foreground dictation state machine and its paste/insertion
path.

Guarantees:
- Single-recorder ownership: recording only starts when an injected
  ``can_acquire_recorder()`` guard says the shared recorder is free (i.e. no
  foreground dictation is active). Otherwise it rejects with a clear reason and
  never silently steals an active recording.
- Explicit observable states (ChatVoiceState) surfaced to the UI.
- Transcription + local correction run OFF the Qt main thread (QThread worker).
- The finalized transcript is handed to a ``submit_fn`` (the ChatPanel) as a
  user message. It is NEVER routed to the clipboard/foreground paste flow.
- Cancellation, panel close and app shutdown stop the worker and release the
  recorder; late worker callbacks are dropped via a monotonic session id.
- Honest failure: empty audio or ASR failure produces an error state, never a
  fake "success".
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal


class ChatVoiceState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    PROCESSING = auto()   # conversation engine handling the submitted text
    ERROR = auto()
    CANCELLED = auto()
    UNAVAILABLE = auto()  # recorder owned by foreground dictation, etc.


class _ChatTranscribeWorker(QObject):
    """Transcribes a captured buffer + applies local correction, off-thread."""

    done = Signal(str, int)      # (corrected_text, session_id)
    failed = Signal(str, int)    # (message, session_id)

    def __init__(self, transcriber, audio: "np.ndarray", sample_rate: int,
                 session_id: int, *, enable_technical: bool, enable_formatting: bool):
        super().__init__()
        self._transcriber = transcriber
        self._audio = audio
        self._sample_rate = sample_rate
        self._session_id = session_id
        self._enable_technical = enable_technical
        self._enable_formatting = enable_formatting

    def run(self) -> None:
        try:
            if self._audio is None or len(self._audio) == 0:
                self.failed.emit("No audio was captured.", self._session_id)
                return
            if not self._transcriber.is_ready:
                # Load the selected, language-compatible model on demand.
                if not self._transcriber.load_model():
                    self.failed.emit("Speech model is unavailable.", self._session_id)
                    return
            raw = self._transcriber.transcribe(self._audio, self._sample_rate)
            if not raw or not raw.strip():
                self.failed.emit("No speech was recognized.", self._session_id)
                return
            # Apply the SAME local transcript-correction pipeline as dictation.
            from ..transcript_processor import correct_transcript

            corrected = correct_transcript(
                raw,
                enable_technical=self._enable_technical,
                enable_formatting=self._enable_formatting,
                enable_structured=self._enable_formatting,
            ).text
            self.done.emit(corrected, self._session_id)
        except Exception as e:  # pragma: no cover - defensive
            self.failed.emit(f"Transcription failed: {e}", self._session_id)


class ChatVoiceController(QObject):
    """Owns the chat voice session lifecycle. Signal-driven; owns no clipboard."""

    state_changed = Signal(object)   # ChatVoiceState
    status_message = Signal(str)
    transcript_ready = Signal(str)   # corrected text -> ChatPanel.submit_text

    def __init__(
        self,
        recorder,
        transcriber,
        *,
        sample_rate: int,
        can_acquire_recorder: Callable[[], bool],
        on_acquire: Callable[[], None],
        on_release: Callable[[], None],
        enable_technical: bool = True,
        enable_formatting: bool = True,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._recorder = recorder
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._can_acquire = can_acquire_recorder
        self._on_acquire = on_acquire
        self._on_release = on_release
        self._enable_technical = enable_technical
        self._enable_formatting = enable_formatting

        self._state = ChatVoiceState.IDLE
        self._session_id = 0
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ChatTranscribeWorker] = None
        self._owns_recorder = False

    @property
    def state(self) -> ChatVoiceState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state in (ChatVoiceState.RECORDING, ChatVoiceState.TRANSCRIBING)

    def _set_state(self, state: ChatVoiceState, message: str = "") -> None:
        self._state = state
        self.state_changed.emit(state)
        if message:
            self.status_message.emit(message)

    # -- public control (toggle) ----------------------------------------
    def toggle(self) -> None:
        """Start if idle, stop if recording (the mic button's single action)."""
        if self._state is ChatVoiceState.RECORDING:
            self.stop()
        elif self._state in (ChatVoiceState.IDLE, ChatVoiceState.ERROR,
                              ChatVoiceState.CANCELLED, ChatVoiceState.UNAVAILABLE):
            self.start()
        # While TRANSCRIBING/PROCESSING, the button is a no-op (UI disables it).

    def start(self) -> None:
        # Single-recorder ownership arbitration: refuse if the shared recorder
        # is busy (foreground dictation active). Never steal it.
        if not self._can_acquire():
            self._set_state(
                ChatVoiceState.UNAVAILABLE,
                "Dictation is using the microphone — finish it first, then try "
                "the assistant again.",
            )
            return
        self._session_id += 1
        try:
            self._on_acquire()
            started = self._recorder.start()
        except Exception as e:
            self._owns_recorder = False
            self._set_state(ChatVoiceState.ERROR, f"Could not start recording: {e}")
            return
        if not started:
            self._owns_recorder = False
            try:
                self._on_release()
            except Exception:
                pass
            err = getattr(self._recorder, "last_error", None) or "Microphone unavailable."
            self._set_state(ChatVoiceState.ERROR, err)
            return
        self._owns_recorder = True
        self._set_state(ChatVoiceState.RECORDING, "Listening…")

    def stop(self) -> None:
        if self._state is not ChatVoiceState.RECORDING:
            return
        audio = None
        try:
            audio = self._recorder.stop()
        except Exception as e:
            self._release_recorder()
            self._set_state(ChatVoiceState.ERROR, f"Recording error: {e}")
            return
        self._release_recorder()
        if audio is None or len(audio) == 0:
            self._set_state(ChatVoiceState.ERROR, "No audio was captured.")
            return
        self._set_state(ChatVoiceState.TRANSCRIBING, "Transcribing…")
        self._start_worker(audio)

    def cancel(self) -> None:
        """Cancel an in-progress recording or transcription. Safe to call any time."""
        self._session_id += 1  # invalidate any in-flight worker result
        if self._state is ChatVoiceState.RECORDING:
            try:
                self._recorder.stop()  # discard the buffer
            except Exception:
                pass
            self._release_recorder()
        self._teardown_worker()
        if self._state is not ChatVoiceState.IDLE:
            self._set_state(ChatVoiceState.CANCELLED, "Cancelled.")

    def shutdown(self) -> None:
        """Release all resources (app shutdown / panel close)."""
        self._session_id += 1
        if self._owns_recorder:
            try:
                self._recorder.stop()
            except Exception:
                pass
            self._release_recorder()
        self._teardown_worker()
        self._state = ChatVoiceState.IDLE

    # -- worker lifecycle -----------------------------------------------
    def _start_worker(self, audio) -> None:
        self._teardown_worker()
        sid = self._session_id
        self._thread = QThread(self)
        self._worker = _ChatTranscribeWorker(
            self._transcriber, audio, self._sample_rate, sid,
            enable_technical=self._enable_technical,
            enable_formatting=self._enable_formatting,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_worker_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_worker_done(self, text: str, session_id: int) -> None:
        if session_id != self._session_id:
            return  # stale (cancelled/superseded) — drop it
        self._set_state(ChatVoiceState.PROCESSING, "Thinking…")
        # Hand off to the conversation engine via the panel. NEVER to clipboard.
        self.transcript_ready.emit(text)
        self._set_state(ChatVoiceState.IDLE)

    def _on_worker_failed(self, message: str, session_id: int) -> None:
        if session_id != self._session_id:
            return
        self._set_state(ChatVoiceState.ERROR, message)

    def _release_recorder(self) -> None:
        if self._owns_recorder:
            self._owns_recorder = False
            try:
                self._on_release()
            except Exception:
                pass

    def _teardown_worker(self) -> None:
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(2000)
            except RuntimeError:
                pass
        self._thread = None
        self._worker = None
