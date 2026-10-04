from unittest.mock import ANY, MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.sayit.app import AppState, TranscribeApp
from src.sayit.core.asr.transcriber import EngineState
from src.sayit.core.input.hotkey import HotkeyListener
from src.sayit.core.settings import HotkeyConfig, Settings
from src.sayit.ui.tray import TrayStatus


@pytest.fixture
def cleanup_app():
    apps = []

    def register(app):
        apps.append(app)
        return app

    yield register

    for app in apps:
        try:
            app._hotkey_listener.stop()
            app._tray.hide()
            app._recording_toast.hide()
            if app._audio_level_timer.isActive():
                app._audio_level_timer.stop()
        except Exception:
            pass

    qapp = QApplication.instance()
    if qapp:
        qapp.processEvents()


@pytest.fixture
def mock_dependencies():
    with (
        patch("src.sayit.app.get_settings") as mock_get_settings,
        patch("src.sayit.app.SystemTray") as MockTray,
        patch("src.sayit.app.AudioRecorder") as MockRecorder,
        patch("src.sayit.app.TranscriptionEngine") as MockTranscriber,
        patch("src.sayit.app.HotkeyListener", wraps=HotkeyListener) as MockHotkey,
        patch("src.sayit.app.set_autostart") as mock_set_autostart,
        patch("src.sayit.app.ModelLoaderThread") as MockLoaderThread,
    ):

        settings = Settings()
        mock_get_settings.return_value = settings

        mock_tray = MockTray.return_value
        mock_recorder = MockRecorder.return_value
        mock_recorder.stop.return_value = b"audio_data"  # Simulate audio captured

        mock_transcriber = MockTranscriber.return_value
        mock_transcriber.transcribe_chunked.return_value = "Hello World"

        mock_loader = MockLoaderThread.return_value
        mock_loader.finished = MagicMock()
        mock_loader.progress = MagicMock()
        mock_loader.state_changed = MagicMock()
        mock_loader.engine = mock_transcriber

        yield {
            "settings": settings,
            "get_settings": mock_get_settings,
            "tray": mock_tray,
            "recorder": mock_recorder,
            "transcriber": mock_transcriber,
            "set_autostart": mock_set_autostart,
            "loader_thread": MockLoaderThread,
        }


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_full_transcription_flow(
    MockWorkerThread,
    MockTextOutput,
    mock_dependencies,
    cleanup_app,
    qtbot,
):

    mock_text_output_instance = MockTextOutput.return_value
    mock_worker_instance = MockWorkerThread.return_value
    mock_worker_instance.finished = MagicMock()
    mock_worker_instance.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    app._start_recording()

    assert app._state == AppState.RECORDING
    mock_dependencies["tray"].set_status.assert_called_with(TrayStatus.RECORDING, "")
    mock_dependencies["recorder"].start.assert_called_once()

    app._stop_recording()
    mock_dependencies["recorder"].stop.assert_called_once()

    MockWorkerThread.assert_called_once()
    mock_worker_instance.start.assert_called_once()

    app._on_transcription_complete(
        app._active_job_id, "Hello World", "Hello World", None, None, None
    )
    mock_text_output_instance.output_text.assert_called_once()
    call_args = mock_text_output_instance.output_text.call_args
    assert (
        call_args[0][0] == "Hello World"
    ), "Text output was not called with transcribed text"


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_overlapping_jobs_are_ignored(
    MockWorkerThread,
    MockTextOutput,
    mock_dependencies,
    cleanup_app,
    qtbot,
):
    mock_worker_instance = MockWorkerThread.return_value
    mock_worker_instance.finished = MagicMock()
    mock_worker_instance.error = MagicMock()
    # Simulate the first worker still running.
    mock_worker_instance.isRunning.return_value = True

    app = cleanup_app(TranscribeApp())

    app._start_recording()
    app._stop_recording()
    assert MockWorkerThread.call_count == 1

    # Second press/release while the first job is still running must NOT spawn
    # a second worker.
    app._start_recording()
    app._stop_recording()
    assert MockWorkerThread.call_count == 1

    # Once the job completes, the worker reference is cleared.
    app._on_transcription_complete(
        app._active_job_id, "Hello", "Hello", None, None, None
    )
    assert app._transcription_worker is None


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_worker_ref_cleared_on_error(
    MockWorkerThread,
    MockTextOutput,
    mock_dependencies,
    cleanup_app,
    qtbot,
):
    mock_worker_instance = MockWorkerThread.return_value
    mock_worker_instance.finished = MagicMock()
    mock_worker_instance.error = MagicMock()
    mock_worker_instance.isRunning.return_value = True

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    assert app._transcription_worker is not None

    app._on_transcription_error(app._active_job_id, "boom")
    assert app._transcription_worker is None


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_stale_result_is_not_inserted(
    MockWorkerThread,
    MockTextOutput,
    mock_dependencies,
    cleanup_app,
    qtbot,
):
    mock_text_output_instance = MockTextOutput.return_value
    mock_worker_instance = MockWorkerThread.return_value
    mock_worker_instance.finished = MagicMock()
    mock_worker_instance.error = MagicMock()
    mock_worker_instance.isRunning.return_value = False

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    current_job = app._active_job_id

    # A completion signal from an OLDER job (id - 1) must be discarded and must
    # NOT insert text into the current context.
    stale_job = current_job - 1
    app._on_transcription_complete(
        stale_job, "stale text", "stale text", None, None, None
    )
    mock_text_output_instance.output_text.assert_not_called()
    # The active job is still intact.
    assert app._active_job_id == current_job

    # A stale error is likewise ignored and does not clear the active job.
    app._on_transcription_error(stale_job, "stale error")
    assert app._active_job_id == current_job

    # The correct job still completes normally.
    app._on_transcription_complete(
        current_job, "real text", "real text", None, None, None
    )
    mock_text_output_instance.output_text.assert_called_once()
    assert app._active_job_id is None


def test_settings_hotkey_update(mock_dependencies, cleanup_app, qtbot):
    with patch("src.sayit.app.HotkeyListener") as MockListener:
        mock_listener_instance = MockListener.return_value

        app = cleanup_app(TranscribeApp())

        new_settings = Settings(hotkey=HotkeyConfig(key="k", modifiers=["ctrl"]))
        mock_dependencies["get_settings"].return_value = new_settings

        app._on_settings_changed()
        mock_listener_instance.update_settings.assert_called_with(new_settings)


def test_autostart_update(mock_dependencies, cleanup_app, qtbot):

    with patch("src.sayit.app.HotkeyListener") as MockListener:
        app = cleanup_app(TranscribeApp())

        new_settings = Settings(auto_start_on_login=True)
        mock_dependencies["get_settings"].return_value = new_settings

        app._on_settings_changed()
        mock_dependencies["set_autostart"].assert_called_with(True, "SayIt")


# ===========================================================================
# Phase 2: state machine, cancellation, engine reload, shutdown
# ===========================================================================


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_state_idle_to_recording_to_transcribing(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    assert app._state == AppState.IDLE

    app._start_recording()
    assert app._state == AppState.RECORDING

    app._stop_recording()
    assert app._state == AppState.TRANSCRIBING

    app._on_transcription_complete(
        app._active_job_id, "hi", "hi", None, None, None
    )
    assert app._state == AppState.IDLE


@patch("src.sayit.app.TranscriptionWorkerThread")
def test_recording_failure_recovers_to_error(
    MockWorkerThread, mock_dependencies, cleanup_app, qtbot
):
    # Recorder fails to start -> must not remain RECORDING.
    mock_dependencies["recorder"].start.return_value = False
    mock_dependencies["recorder"].last_error = "mic busy"

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    assert app._state == AppState.ERROR
    # Recoverable: a subsequent start is allowed from ERROR.
    mock_dependencies["recorder"].start.return_value = True
    app._start_recording()
    assert app._state == AppState.RECORDING


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_transcription_failure_recovers_to_error(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    job = app._active_job_id

    app._on_transcription_error(job, "engine failed")
    assert app._state == AppState.ERROR
    assert app._active_job_id is None


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_insertion_failure_leaves_recoverable_error(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    from src.sayit.core.output.text_output import InsertionResult

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    text_out = MockTextOutput.return_value
    # Copy failed -> not inserted, but transcript recoverable (in history).
    text_out.output_text.return_value = InsertionResult(
        copied=False, paste_issued=False, text="hi"
    )

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    app._on_transcription_complete(
        app._active_job_id, "hi", "hi", None, None, None
    )
    assert app._state == AppState.ERROR


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_esc_cancels_recording(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    assert app._state == AppState.RECORDING

    app._cancel_current()  # Esc

    assert app._state == AppState.IDLE
    mock_dependencies["recorder"].stop.assert_called()
    # No transcription worker was created for the cancelled recording.
    MockWorkerThread.assert_not_called()


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_esc_cancels_transcription_and_invalidates_job(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    text_out = MockTextOutput.return_value

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    assert app._state == AppState.TRANSCRIBING
    cancelled_job = app._active_job_id

    app._cancel_current()  # Esc during transcription
    assert app._state == AppState.IDLE
    assert app._active_job_id is None
    mw.cancel.assert_called_once()

    # The worker eventually completes; its (now stale) result must NOT insert.
    app._on_transcription_complete(
        cancelled_job, "stale", "stale", None, None, None
    )
    text_out.output_text.assert_not_called()


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_cancelled_job_then_new_job_late_signal_ignored(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    mw.isRunning.return_value = False
    text_out = MockTextOutput.return_value

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    job_a = app._active_job_id

    app._cancel_current()  # cancel job A
    assert app._active_job_id is None

    # New dictation starts (job B).
    app._start_recording()
    app._stop_recording()
    job_b = app._active_job_id
    assert job_b != job_a

    # Late completion from cancelled job A must be ignored; job B stays active.
    app._on_transcription_complete(job_a, "A", "A", None, None, None)
    text_out.output_text.assert_not_called()
    assert app._active_job_id == job_b

    # Job B completes normally.
    app._on_transcription_complete(job_b, "B", "B", None, None, None)
    text_out.output_text.assert_called_once()


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_engine_reload_while_transcribing_invalidates_job(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    mw.isRunning.return_value = True
    text_out = MockTextOutput.return_value

    with patch("src.sayit.app.ModelLoaderThread"):
        app = cleanup_app(TranscribeApp())
        app._start_recording()
        app._stop_recording()
        stale_job = app._active_job_id
        assert app._state == AppState.TRANSCRIBING

        # Change the model id so _on_settings_changed triggers a reload.
        new_settings = Settings(model_id="sherpa-onnx-whisper-tiny")
        mock_dependencies["get_settings"].return_value = new_settings
        app._on_settings_changed()

        # Active job invalidated, worker asked to cancel and waited on.
        assert app._active_job_id is None
        mw.cancel.assert_called_once()
        mw.wait.assert_called_once()

        # A late completion from the pre-reload job must not insert.
        app._on_transcription_complete(
            stale_job, "old", "old", None, None, None
        )
        text_out.output_text.assert_not_called()


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_shutdown_during_transcription_invalidates_and_blocks(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    mw.isRunning.return_value = True
    text_out = MockTextOutput.return_value

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    stale_job = app._active_job_id

    with patch("src.sayit.app.QApplication"):
        app._quit()

    assert app._state == AppState.SHUTTING_DOWN
    assert app._active_job_id is None
    mw.cancel.assert_called_once()

    # No new recording may start after shutdown.
    app._start_recording()
    assert app._state == AppState.SHUTTING_DOWN

    # Late completion after shutdown must not insert.
    app._on_transcription_complete(stale_job, "x", "x", None, None, None)
    text_out.output_text.assert_not_called()


@patch("src.sayit.app.TranscriptionWorkerThread")
def test_shutdown_during_recording_stops_recorder(
    MockWorkerThread, mock_dependencies, cleanup_app, qtbot
):
    mock_dependencies["recorder"].is_recording = True

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    assert app._state == AppState.RECORDING

    with patch("src.sayit.app.QApplication"):
        app._quit()

    assert app._state == AppState.SHUTTING_DOWN
    mock_dependencies["recorder"].stop.assert_called()



# ===========================================================================
# Phase 3: privacy defaults (history opt-in) + transient recovery
# ===========================================================================


@patch("src.sayit.app.add_history_record")
@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_history_not_persisted_when_disabled(
    MockWorkerThread, MockTextOutput, mock_add_history, mock_dependencies,
    cleanup_app, qtbot,
):
    from src.sayit.core.output.text_output import InsertionResult

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    MockTextOutput.return_value.output_text.return_value = InsertionResult(
        copied=True, paste_issued=True, text="hello"
    )

    # Default settings have history disabled.
    assert mock_dependencies["settings"].history_enabled is False

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    app._on_transcription_complete(
        app._active_job_id, "hello", "hello", None, None, None
    )

    # Nothing persisted to history...
    mock_add_history.assert_not_called()
    # ...but the transcript is kept in memory for recovery.
    assert app._last_transcript == "hello"


@patch("src.sayit.app.add_history_record")
@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_history_persisted_when_enabled(
    MockWorkerThread, MockTextOutput, mock_add_history, mock_dependencies,
    cleanup_app, qtbot,
):
    from src.sayit.core.output.text_output import InsertionResult

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    MockTextOutput.return_value.output_text.return_value = InsertionResult(
        copied=True, paste_issued=True, text="hello"
    )
    mock_dependencies["settings"].history_enabled = True

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    app._on_transcription_complete(
        app._active_job_id, "hello", "hello", None, None, None
    )

    mock_add_history.assert_called_once()


@patch("src.sayit.app.add_history_record")
@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_failed_insertion_recoverable_without_history(
    MockWorkerThread, MockTextOutput, mock_add_history, mock_dependencies,
    cleanup_app, qtbot,
):
    from src.sayit.core.output.text_output import InsertionResult

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    # Insertion fails entirely (copy failed).
    MockTextOutput.return_value.output_text.return_value = InsertionResult(
        copied=False, paste_issued=False, text="precious"
    )
    assert mock_dependencies["settings"].history_enabled is False

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()
    app._on_transcription_complete(
        app._active_job_id, "precious", "precious", None, None, None
    )

    # Even with history off and insertion failed, the transcript is recoverable
    # in memory and the app is in a visible ERROR state (not lost silently).
    assert app._last_transcript == "precious"
    assert app._state == AppState.ERROR
    mock_add_history.assert_not_called()



@patch("src.sayit.app.TranscriptionWorkerThread")
def test_cloud_enhancement_off_by_default(
    MockWorkerThread, mock_dependencies, cleanup_app, qtbot
):
    # A fresh install must not initialize any cloud LLM processor: default
    # provider has no API key and no active enhancement, so enhancement is inert.
    app = cleanup_app(TranscribeApp())
    assert app._llm_processor is None
    assert app._settings.active_enhancement_id is None



# ===========================================================================
# Live Home state wiring
# ===========================================================================


def _home_state_name(app):
    return app._settings_window.home_tab._state.name


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_home_reflects_workflow_states(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    from src.sayit.ui.main_window import SettingsWindow

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    # Attach a real settings window so Home exists.
    win = SettingsWindow()
    qtbot.addWidget(win)
    app._settings_window = win

    app._set_state(AppState.IDLE)
    assert _home_state_name(app) == "IDLE"

    app._set_state(AppState.RECORDING)
    assert _home_state_name(app) == "LISTENING"

    app._set_state(AppState.TRANSCRIBING)
    assert _home_state_name(app) == "TRANSCRIBING"

    app._set_state(AppState.CANCELLED)
    assert _home_state_name(app) == "IDLE"

    # Error maps to IDLE on Home (no dedicated Home error state).
    app._set_state(AppState.ERROR, "boom")
    assert _home_state_name(app) == "IDLE"


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_home_shows_real_transcript_on_success(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    from src.sayit.core.output.text_output import InsertionResult
    from src.sayit.ui.main_window import SettingsWindow

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()
    MockTextOutput.return_value.output_text.return_value = InsertionResult(
        copied=True, paste_issued=True, text="hello world"
    )

    app = cleanup_app(TranscribeApp())
    win = SettingsWindow()
    qtbot.addWidget(win)
    app._settings_window = win

    app._start_recording()
    app._stop_recording()
    app._on_transcription_complete(
        app._active_job_id, "hello world", "hello world", None, None, None
    )

    home = win.home_tab
    assert home._transcript.text() == "hello world"
    assert home._transcript.isHidden() is False
    # Final state line is back to IDLE, but the transcript card is preserved.
    assert home._state.name == "IDLE"


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_home_update_safe_without_window(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    assert app._settings_window is None
    # Must not raise when no window exists.
    app._set_state(AppState.RECORDING)
    app._update_home(AppState.IDLE, transcript="x")


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_home_update_noop_during_shutdown(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    from src.sayit.ui.main_window import SettingsWindow

    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    win = SettingsWindow()
    qtbot.addWidget(win)
    app._settings_window = win
    app._set_state(AppState.IDLE)

    # Enter shutdown; subsequent updates must be no-ops and must not raise.
    app._set_state(AppState.SHUTTING_DOWN)
    app._update_home(AppState.RECORDING)
    assert app._state == AppState.SHUTTING_DOWN


# ===========================================================================
# Phase 6B: timing instrumentation, mic failure, empty-audio safety
# ===========================================================================


@patch("src.sayit.app.TextOutputController")
@patch("src.sayit.app.TranscriptionWorkerThread")
def test_timing_fields_set_on_dictation(
    MockWorkerThread, MockTextOutput, mock_dependencies, cleanup_app, qtbot
):
    mw = MockWorkerThread.return_value
    mw.finished = MagicMock()
    mw.error = MagicMock()

    app = cleanup_app(TranscribeApp())
    assert app._recording_started_at is None

    app._start_recording()
    assert app._recording_started_at is not None

    app._stop_recording()
    # Transcription start stamp is set when the worker launches.
    assert app._transcribe_started_at is not None


@patch("src.sayit.app.TranscriptionWorkerThread")
def test_microphone_failure_is_safe(
    MockWorkerThread, mock_dependencies, cleanup_app, qtbot
):
    # Recorder cannot start (device unavailable): must not get stuck RECORDING.
    mock_dependencies["recorder"].start.return_value = False
    mock_dependencies["recorder"].last_error = "no input device"

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    assert app._state == AppState.ERROR
    # No worker was created.
    MockWorkerThread.assert_not_called()
    # Recoverable: a later successful start works.
    mock_dependencies["recorder"].start.return_value = True
    app._start_recording()
    assert app._state == AppState.RECORDING


@patch("src.sayit.app.TranscriptionWorkerThread")
def test_empty_audio_creates_no_job(
    MockWorkerThread, mock_dependencies, cleanup_app, qtbot
):
    # Recorder returns no audio (silence / empty capture).
    mock_dependencies["recorder"].stop.return_value = None

    app = cleanup_app(TranscribeApp())
    app._start_recording()
    app._stop_recording()

    # No transcription job spawned; back to IDLE; no stale state.
    MockWorkerThread.assert_not_called()
    assert app._state == AppState.IDLE
    assert app._active_job_id is None



# ===========================================================================
# Phase 6E: default model + safe startup fallback
# ===========================================================================


def test_default_model_is_parakeet_int8():
    from src.sayit.core.settings import Settings
    from src.sayit.core.settings.settings import (
        DEFAULT_MODEL_ID,
        FALLBACK_MODEL_ID,
    )

    assert DEFAULT_MODEL_ID == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
    assert FALLBACK_MODEL_ID == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
    assert Settings().model_id == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"


@patch("src.sayit.app.ModelLoaderThread")
def test_startup_load_failure_falls_back(
    MockLoader, mock_dependencies, cleanup_app, qtbot
):
    # Each ModelLoaderThread instance is a fresh mock.
    instances = []

    def make(*a, **k):
        m = MagicMock()
        m.model_name = k.get("model_name")
        m.state_changed = MagicMock()
        m.progress = MagicMock()
        m.finished = MagicMock()
        m.isRunning.return_value = False
        instances.append(m)
        return m

    MockLoader.side_effect = make

    app = cleanup_app(TranscribeApp())

    # Simulate a startup (non-user-initiated) load of a model that fails.
    app._start_model_loading("sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16", user_initiated=False)
    assert app._loading_model_id == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16"

    app._on_model_loaded(False, "bad allocation")

    # It fell back to the known-compatible int8 model (one more loader created).
    assert app._fallback_attempted is True
    assert app._loading_model_id == "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"


@patch("src.sayit.app.ModelLoaderThread")
def test_explicit_user_selection_failure_not_overridden(
    MockLoader, mock_dependencies, cleanup_app, qtbot
):
    created = []

    def make(*a, **k):
        m = MagicMock()
        m.state_changed = MagicMock()
        m.progress = MagicMock()
        m.finished = MagicMock()
        m.isRunning.return_value = False
        created.append(k.get("model_name"))
        return m

    MockLoader.side_effect = make

    app = cleanup_app(TranscribeApp())
    app._start_model_loading("some/user-chosen-model", user_initiated=True)
    n_before = len(created)

    app._on_model_loaded(False, "init failed")

    # No silent fallback for an explicit user selection; error state shown.
    assert app._fallback_attempted is False
    assert len(created) == n_before  # no extra loader was started
    assert app._state == AppState.ERROR


@patch("src.sayit.app.ModelLoaderThread")
def test_fallback_does_not_loop_when_fallback_itself_fails(
    MockLoader, mock_dependencies, cleanup_app, qtbot
):
    def make(*a, **k):
        m = MagicMock()
        m.state_changed = MagicMock()
        m.progress = MagicMock()
        m.finished = MagicMock()
        m.isRunning.return_value = False
        return m

    MockLoader.side_effect = make

    app = cleanup_app(TranscribeApp())
    # Startup load of the fallback model itself fails -> must NOT retry forever.
    app._start_model_loading(
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8", user_initiated=False
    )
    app._on_model_loaded(False, "init failed")
    assert app._state == AppState.ERROR
