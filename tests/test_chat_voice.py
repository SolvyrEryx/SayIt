"""ChatVoiceController tests (mocked recorder + ASR; no real microphone).

These validate the voice-to-chat lifecycle, single-recorder ownership, honest
errors, cancellation/shutdown cleanup, late-callback rejection, and that the
corrected transcript is emitted for chat submission (never a foreground paste).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from sayit.core.conversation.voice_controller import (  # noqa: E402
    ChatVoiceController,
    ChatVoiceState,
    _ChatTranscribeWorker,
)


def _app():
    return QApplication.instance() or QApplication([])


class _FakeRecorder:
    def __init__(self, audio=None, start_ok=True, last_error=None):
        self._audio = audio if audio is not None else np.ones(16000, dtype=np.float32)
        self._start_ok = start_ok
        self.last_error = last_error
        self.started = False
        self.stopped = False

    def start(self):
        self.started = self._start_ok
        return self._start_ok

    def stop(self):
        self.stopped = True
        return self._audio


class _FakeTranscriber:
    def __init__(self, text="hello world", ready=True, load_ok=True):
        self._text = text
        self.is_ready = ready
        self._load_ok = load_ok
        self.calls = []

    def load_model(self):
        self.is_ready = self._load_ok
        return self._load_ok

    def transcribe(self, audio, sample_rate=16000):
        self.calls.append((len(audio), sample_rate))
        return self._text


def _controller(recorder, transcriber, *, can_acquire=True):
    acquired = {"n": 0}
    released = {"n": 0}
    c = ChatVoiceController(
        recorder, transcriber, sample_rate=16000,
        can_acquire_recorder=lambda: can_acquire,
        on_acquire=lambda: acquired.__setitem__("n", acquired["n"] + 1),
        on_release=lambda: released.__setitem__("n", released["n"] + 1),
    )
    return c, acquired, released


# --- ownership arbitration --------------------------------------------------
def test_rejects_when_recorder_busy():
    _app()
    rec = _FakeRecorder()
    c, acq, rel = _controller(rec, _FakeTranscriber(), can_acquire=False)
    c.start()
    assert c.state is ChatVoiceState.UNAVAILABLE
    assert rec.started is False          # never started
    assert acq["n"] == 0                 # never acquired the shared recorder


def test_start_acquires_and_records():
    _app()
    rec = _FakeRecorder()
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c.start()
    assert c.state is ChatVoiceState.RECORDING
    assert rec.started is True
    assert acq["n"] == 1


def test_start_failure_releases_and_errors():
    _app()
    rec = _FakeRecorder(start_ok=False, last_error="Microphone unavailable.")
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c.start()
    assert c.state is ChatVoiceState.ERROR
    assert rel["n"] == 1                 # released after failed start


# --- end-to-end recording -> transcript (off-thread) ------------------------
def test_stop_transcribes_and_emits_corrected_text(qtbot):
    _app()
    rec = _FakeRecorder()
    tr = _FakeTranscriber(text="we deployed with git hub actions")
    c, acq, rel = _controller(rec, tr)

    # Run the transcription worker synchronously for a deterministic headless
    # test (real cross-thread QThread timing is flaky in CI). This still drives
    # the full start -> stop -> worker -> _on_worker_done -> transcript_ready path
    # using the REAL _ChatTranscribeWorker + _on_worker_done handler.
    def _sync_start_worker(audio):
        w = _ChatTranscribeWorker(
            c._transcriber, audio, c._sample_rate, c._session_id,
            enable_technical=c._enable_technical, enable_formatting=c._enable_formatting,
        )
        w.done.connect(c._on_worker_done)
        w.failed.connect(c._on_worker_failed)
        w.run()
    c._start_worker = _sync_start_worker

    got = []
    c.transcript_ready.connect(lambda t: got.append(t))
    c.start()
    c.stop()
    # Local transcript correction was applied (GitHub), proving reuse of the
    # SAME correction pipeline as dictation.
    assert got and "GitHub" in got[0]
    assert rec.stopped is True
    assert rel["n"] == 1                 # recorder released after stop


def test_empty_audio_is_honest_error():
    _app()
    rec = _FakeRecorder(audio=np.array([], dtype=np.float32))
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c.start()
    c.stop()
    assert c.state is ChatVoiceState.ERROR


# --- worker-level behaviour (deterministic, synchronous) --------------------
def test_worker_no_speech_fails_honestly(qtbot):
    _app()
    w = _ChatTranscribeWorker(_FakeTranscriber(text=""), np.ones(16000, dtype=np.float32),
                              16000, session_id=1, enable_technical=True, enable_formatting=True)
    failures = []
    w.failed.connect(lambda m, s: failures.append(m))
    w.run()
    assert failures and "recognized" in failures[0].lower()


def test_worker_loads_model_when_not_ready(qtbot):
    _app()
    tr = _FakeTranscriber(text="hi", ready=False, load_ok=True)
    w = _ChatTranscribeWorker(tr, np.ones(16000, dtype=np.float32), 16000,
                              session_id=1, enable_technical=False, enable_formatting=False)
    done = []
    w.done.connect(lambda t, s: done.append(t))
    w.run()
    assert done == ["hi"]
    assert tr.is_ready is True


def test_worker_model_unavailable_fails(qtbot):
    _app()
    tr = _FakeTranscriber(text="hi", ready=False, load_ok=False)
    w = _ChatTranscribeWorker(tr, np.ones(16000, dtype=np.float32), 16000,
                              session_id=1, enable_technical=False, enable_formatting=False)
    failures = []
    w.failed.connect(lambda m, s: failures.append(m))
    w.run()
    assert failures and "unavailable" in failures[0].lower()


# --- late-callback / stale session rejection --------------------------------
def test_late_callback_rejected():
    _app()
    rec = _FakeRecorder()
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c._session_id = 5
    emitted = []
    c.transcript_ready.connect(lambda t: emitted.append(t))
    # A worker result from an OLD session id must be dropped.
    c._on_worker_done("stale text", session_id=3)
    assert emitted == []


# --- cancellation + shutdown ------------------------------------------------
def test_cancel_during_recording_releases():
    _app()
    rec = _FakeRecorder()
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c.start()
    c.cancel()
    assert c.state is ChatVoiceState.CANCELLED
    assert rel["n"] == 1
    assert rec.stopped is True


def test_shutdown_releases_everything():
    _app()
    rec = _FakeRecorder()
    c, acq, rel = _controller(rec, _FakeTranscriber())
    c.start()
    c.shutdown()
    assert c.state is ChatVoiceState.IDLE
    assert rel["n"] == 1


# --- no foreground insertion -------------------------------------------------
def test_controller_never_touches_clipboard_or_paste():
    # The controller has no reference to any TextOutputController / pyperclip.
    import sayit.core.conversation.voice_controller as vc
    src = open(vc.__file__, encoding="utf-8").read()
    assert "pyperclip" not in src
    assert "TextOutputController" not in src
    assert "output_text" not in src
