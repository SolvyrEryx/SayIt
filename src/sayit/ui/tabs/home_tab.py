from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import __display_name__
from ...core.settings import get_settings
from ...core.settings.data_manager import (
    get_all_data_paths,
    schedule_cleanup_and_exit,
)
from ..theme import sayit_mark
from .privacy_tab import enhancement_sends_transcript_to_cloud


class HomeState(Enum):
    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    COMPLETE = auto()


class HomeTab(QWidget):
    """Minimal, voice-first home surface.

    Communicates the single core interaction at a glance (hold Ctrl + Space and
    speak) and reflects the current workflow state. It renders state passed in
    via ``set_state`` — it does not own or drive the application state machine.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = HomeState.IDLE
        self._setup_ui()
        self.set_state(HomeState.IDLE)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 20)
        root.setSpacing(0)

        root.addStretch(1)

        # SayIt mark.
        self._logo = QLabel()
        self._logo.setPixmap(sayit_mark(56))
        self._logo.setAlignment(Qt.AlignCenter)
        self._logo.setAccessibleName(f"{__display_name__} logo")
        root.addWidget(self._logo, alignment=Qt.AlignCenter)

        root.addSpacing(10)

        # Wordmark.
        wordmark = QLabel(__display_name__)
        wordmark.setAlignment(Qt.AlignCenter)
        wordmark.setStyleSheet("font-size: 22px; font-weight: 700; letter-spacing: 0.3px;")
        root.addWidget(wordmark)

        root.addSpacing(18)

        # Primary state line.
        self._state_label = QLabel("Ready to speak")
        self._state_label.setAlignment(Qt.AlignCenter)
        self._state_label.setStyleSheet("font-size: 17px; font-weight: 600;")
        self._state_label.setAccessibleName("Current status")
        root.addWidget(self._state_label)

        root.addSpacing(6)

        # Instruction / hint line.
        self._hint_label = QLabel("Hold  Ctrl + Space  to dictate")
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet("font-size: 13px; color: rgba(128,128,128,210);")
        root.addWidget(self._hint_label)

        root.addSpacing(10)

        # Phase 8A: current context/profile indicator. Communicates when an
        # automatic context decision is active (e.g. 'Auto · code') versus a
        # resolved profile. Hidden until the first resolution so it never shows
        # a misleading default. Purely informational.
        self._context_label = QLabel("")
        self._context_label.setAlignment(Qt.AlignCenter)
        self._context_label.setObjectName("HomeContext")
        self._context_label.setAccessibleName("Current context")
        self._context_label.setStyleSheet(
            "QLabel#HomeContext {"
            " font-size: 12px; font-weight: 600;"
            " color: rgba(128,128,128,230);"
            " border: 1px solid rgba(128,128,128,70); border-radius: 10px;"
            " padding: 3px 10px; }"
        )
        self._context_label.hide()
        root.addWidget(self._context_label, alignment=Qt.AlignCenter)

        # Subtle current-speech-mode status (e.g. 'Fast · Parakeet INT8').
        self._mode_label = QLabel("")
        self._mode_label.setAlignment(Qt.AlignCenter)
        self._mode_label.setObjectName("HomeMode")
        self._mode_label.setAccessibleName("Current speech mode")
        self._mode_label.setStyleSheet(
            "QLabel#HomeMode { font-size: 11px; color: rgba(128,128,128,180); }"
        )
        self._mode_label.hide()
        root.addWidget(self._mode_label, alignment=Qt.AlignCenter)

        root.addSpacing(16)

        # Transcript area (hidden until there is a real transcript).
        self._transcript = QLabel("")
        self._transcript.setWordWrap(True)
        self._transcript.setAlignment(Qt.AlignCenter)
        self._transcript.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._transcript.setObjectName("HomeTranscript")
        self._transcript.setAccessibleName("Latest transcript")
        self._transcript.setStyleSheet(
            "QLabel#HomeTranscript {"
            " border: 1px solid rgba(128,128,128,60); border-radius: 10px;"
            " padding: 12px 14px; font-size: 14px; }"
        )
        self._transcript.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._transcript.hide()
        root.addWidget(self._transcript)

        # Subtle local-processing note (only shown when accurate).
        self._privacy_note = QLabel("")
        self._privacy_note.setAlignment(Qt.AlignCenter)
        self._privacy_note.setStyleSheet("font-size: 11px; color: rgba(128,128,128,170);")
        root.addSpacing(10)
        root.addWidget(self._privacy_note)

        root.addStretch(2)

        # Clear data lives at the very bottom, visually subordinate.
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Plain)
        separator.setStyleSheet("color: rgba(128,128,128,50);")
        root.addWidget(separator)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self._clear_data_btn = QPushButton("Clear Data…")
        self._clear_data_btn.setAccessibleName("Clear data")
        self._clear_data_btn.clicked.connect(self._on_clear_data_clicked)
        bottom.addWidget(self._clear_data_btn)
        root.addLayout(bottom)

    def set_state(self, state: "HomeState", transcript: Optional[str] = None) -> None:
        """Render one of the home states. ``transcript`` is only used for COMPLETE."""
        from ..motion import NORMAL, crossfade_text, fade_in

        self._state = state

        if state == HomeState.IDLE:
            crossfade_text(self._state_label, "Ready to speak")
            self._hint_label.setText("Hold  Ctrl + Space  to dictate")
            self._hint_label.show()
        elif state == HomeState.LISTENING:
            crossfade_text(self._state_label, "Listening…")
            self._hint_label.setText("Release to transcribe  ·  Esc to cancel")
            self._hint_label.show()
        elif state == HomeState.TRANSCRIBING:
            crossfade_text(self._state_label, "Transcribing…")
            self._hint_label.setText("")
            self._hint_label.hide()
        elif state == HomeState.COMPLETE:
            crossfade_text(self._state_label, "Ready to speak")
            self._hint_label.setText("Hold  Ctrl + Space  to dictate")
            self._hint_label.show()

        # Show the real transcript when provided; never fabricate one. The card
        # fades in as a single coherent surface.
        if state == HomeState.COMPLETE and transcript:
            self._transcript.setText(transcript)
            fade_in(self._transcript, NORMAL)
        elif state in (HomeState.LISTENING, HomeState.TRANSCRIBING):
            self._transcript.hide()

        self._refresh_privacy_note()

    def set_context(self, display: str) -> None:
        """Show the current context/profile string, e.g. 'Developer' or
        'Auto · code'. Called by the app after each context resolution.

        Informational only; it never drives any workflow state. A subtle
        crossfade reuses the existing motion system.
        """
        if not display:
            self._context_label.hide()
            return
        from ..motion import crossfade_text

        text = f"Context: {display}"
        if self._context_label.isVisible():
            crossfade_text(self._context_label, text)
        else:
            self._context_label.setText(text)
            self._context_label.show()

    def set_speech_mode(self, status: str) -> None:
        """Show the subtle current speech-mode status, e.g.
        'Fast · Parakeet INT8' or 'Higher Accuracy · Whisper Small'.
        Informational only; never drives workflow state."""
        if not status:
            self._mode_label.hide()
            return
        self._mode_label.setText(status)
        self._mode_label.show()

    def set_protected(self, app_label: str) -> None:
        """Show an unmistakable 'protected application' state. Phase 8E.

        Called when recording was blocked by a Safe Zone. Reuses the context
        chip with a warning tint so the paused state is obvious.
        """
        from ..motion import crossfade_text

        text = "SayIt paused — protected application"
        if app_label:
            text = f"SayIt paused — protected: {app_label}"
        self._context_label.setStyleSheet(
            "QLabel#HomeContext {"
            " font-size: 12px; font-weight: 700;"
            " color: #b9770e;"
            " border: 1px solid rgba(185,119,14,120); border-radius: 10px;"
            " padding: 3px 10px; }"
        )
        if self._context_label.isVisible():
            crossfade_text(self._context_label, text)
        else:
            self._context_label.setText(text)
            self._context_label.show()

    def set_edit_note(self, note: str) -> None:
        """Briefly show a voice-edit note (e.g. 'Replaced "five" with "six"').

        Phase 8B/8H. Non-intrusive: reuses the hint line, which returns to the
        default instruction on the next state change.
        """
        if not note:
            return
        from ..motion import crossfade_text

        crossfade_text(self._hint_label, f"Voice edit: {note}")
        self._hint_label.show()

    def _refresh_privacy_note(self) -> None:
        # Only claim local processing when the current config does not send
        # transcript text to a cloud provider.
        try:
            settings = get_settings()
            if not enhancement_sends_transcript_to_cloud(settings):
                self._privacy_note.setText("Your voice is transcribed on this device")
            else:
                self._privacy_note.setText(
                    "Cloud enhancement is on — transcript text is sent to your provider"
                )
        except Exception:
            self._privacy_note.setText("")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_privacy_note()

    def _on_clear_data_clicked(self) -> None:
        paths = get_all_data_paths()
        if not paths:
            QMessageBox.information(
                self,
                "Nothing to Remove",
                f"No {__display_name__} data was found.",
            )
            return

        paths_list = "\n".join(f"  • {p}" for p in paths)
        reply = QMessageBox.warning(
            self,
            f"Clear all {__display_name__} data?",
            f"This will permanently delete the following and cannot be undone:\n\n"
            f"{paths_list}\n\n"
            f"{__display_name__} will close immediately and the data will be "
            "removed in the background. You will need to set it up again, "
            "including re-downloading a speech model.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )

        if reply != QMessageBox.Yes:
            return

        schedule_cleanup_and_exit()
        QApplication.quit()
