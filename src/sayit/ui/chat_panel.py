"""Conversational assistant panel for SayIt (Workstream B).

A focused, desktop-native chat surface built on the existing PySide6 stack and
SayIt's theme/motion. It is intentionally signal-driven and owns NO recorder,
provider, or clipboard itself:

* Text input is handled locally+off-thread through a ChatWorker.
* Voice input emits ``voice_requested``; the app drives the SAME recording
  pipeline it already uses, with the CHAT destination, and calls
  :meth:`submit_text` with the finalized transcript. Ordinary dictation stays
  completely separate (destination-based routing).
* The conversational turn runs the local ConversationEngine (authoritative,
  fast); optional cloud enrichment runs OFF the GUI thread so inference/provider
  calls never block the UI. Each turn is revision-aware so a stale async reply
  cannot overwrite a newer correction.

There is no Online/Offline switch — the orchestrator decides cloud eligibility
behind the scenes from existing privacy/provider settings.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __display_name__
from .theme import ACCENT, STYLESHEET


class ChatWorker(QObject):
    """Runs one conversation turn off the GUI thread.

    Emits ``finished(reply_dict, turn_id)`` where ``turn_id`` lets the panel
    discard a stale result (revision-aware async). Never raises into the GUI:
    provider failures come back as a local reply via the orchestrator.
    """

    finished = Signal(dict, int)
    failed = Signal(str, int)

    def __init__(self, orchestrator, text: str, turn_id: int):
        super().__init__()
        self._orchestrator = orchestrator
        self._text = text
        self._turn_id = turn_id

    def run(self) -> None:
        try:
            reply = self._orchestrator.handle_conversation_turn(self._text)
            self.finished.emit(
                {
                    "text": reply.text,
                    "needs_clarification": reply.needs_clarification,
                    "used_cloud": reply.used_cloud,
                    "cloud_skipped_reason": reply.cloud_skipped_reason,
                },
                self._turn_id,
            )
        except Exception as e:  # pragma: no cover - defensive
            self.failed.emit(str(e), self._turn_id)


class ChatPanel(QWidget):
    """A standalone conversational-assistant window."""

    # Emitted when the user presses the voice button; the app runs the existing
    # recording pipeline (CHAT destination) and calls submit_text() on finish.
    voice_requested = Signal()
    closed = Signal()

    def __init__(self, orchestrator, parent: Optional[QWidget] = None, *, reminder_bridge=None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self._orchestrator = orchestrator
        # Optional ReminderConversationBridge: when present, the panel exposes a
        # "Confirm reminder" action and routes reminder-management phrases
        # (move/rename/cancel/snooze/query) to the authoritative service. When
        # None, the panel behaves exactly as before (no reminder features).
        self._bridge = reminder_bridge
        self._turn_counter = 0
        self._latest_turn_id = 0
        self._thread: Optional[QThread] = None
        self._worker: Optional[ChatWorker] = None

        self.setWindowTitle(f"{__display_name__} — Assistant")
        self.setMinimumSize(380, 480)
        self.setStyleSheet(STYLESHEET)
        self._setup_ui()

    # -- UI --------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setObjectName("SayItChatPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("Assistant")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(title)

        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setPlaceholderText(
            "Ask me to plan a reminder, draft a note, or revise what you said — "
            "e.g. \u201cRemind me about the meeting tomorrow. Scratch that, Friday.\u201d"
        )
        layout.addWidget(self._transcript, 1)

        # Pending-proposal preview, always synced to the latest revision.
        self._proposal = QLabel("")
        self._proposal.setWordWrap(True)
        self._proposal.setStyleSheet(
            f"border: 1px solid {ACCENT}; border-radius: 8px; padding: 6px; "
            "color: palette(text);"
        )
        self._proposal.setVisible(False)
        layout.addWidget(self._proposal)

        # Reminder confirmation actions (only shown when a schedulable reminder
        # proposal is active AND a reminder bridge is wired).
        self._confirm_row = QHBoxLayout()
        self._confirm_btn = QPushButton("Confirm reminder")
        self._confirm_btn.setToolTip("Schedule this reminder")
        self._confirm_btn.clicked.connect(self._on_confirm_reminder)
        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setToolTip("Don't schedule; keep revising in chat")
        self._dismiss_btn.clicked.connect(self._on_dismiss_reminder)
        self._confirm_row.addWidget(self._confirm_btn)
        self._confirm_row.addWidget(self._dismiss_btn)
        self._confirm_row.addStretch()
        self._confirm_widget = QWidget()
        self._confirm_widget.setLayout(self._confirm_row)
        self._confirm_widget.setVisible(False)
        layout.addWidget(self._confirm_widget)

        self._status = QLabel("")
        self._status.setStyleSheet("color: rgba(128,128,128,200); font-size: 11px;")
        layout.addWidget(self._status)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message…")
        self._input.returnPressed.connect(self._on_send)
        row.addWidget(self._input, 1)

        self._voice_btn = QPushButton("🎙")
        self._voice_btn.setToolTip("Speak (uses local transcription)")
        self._voice_btn.clicked.connect(self.voice_requested.emit)
        row.addWidget(self._voice_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._send_btn)
        layout.addLayout(row)

        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.close)

    # -- public API ------------------------------------------------------
    def submit_text(self, text: str) -> None:
        """Submit a user message (from typing or finished voice transcription)."""
        text = (text or "").strip()
        if not text:
            return
        self._append("You", text)
        self._input.clear()

        # Reminder MANAGEMENT intents (move/rename/cancel/snooze/query an
        # ALREADY-scheduled reminder) are handled by the authoritative service
        # via the bridge — the SAME path for typed and spoken input. A creation
        # request is NOT handled here; it flows through the ordinary turn and
        # surfaces a Confirm button (explicit confirmation required).
        if self._bridge is not None:
            try:
                br = self._bridge.handle_turn(text)
            except Exception as e:  # pragma: no cover - defensive
                br = None
                self._append("Assistant", f"Reminder update failed: {e}")
            if br is not None and br.handled:
                self._append("Assistant", br.text)
                self._set_status("Needs clarification." if br.needs_clarification
                                 else "Done.")
                self._sync_proposal()
                return

        self._run_turn(text)

    def focus_input(self) -> None:
        self._input.setFocus()

    # -- voice state reflection (from ChatVoiceController) ---------------
    def set_voice_state(self, state) -> None:
        """Reflect the ChatVoiceState on the mic button + input enablement.

        ``state`` is a ChatVoiceState enum; we read its ``.name`` so this panel
        has no hard import dependency on the controller.
        """
        name = getattr(state, "name", str(state))
        recording = name == "RECORDING"
        busy = name in ("TRANSCRIBING", "PROCESSING")
        self._voice_btn.setText("■ Stop" if recording else "🎙")
        # While transcribing/processing, typing+voice are disabled (no overlap).
        self._voice_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        if name == "RECORDING":
            self._set_status("Listening… press the mic again to stop.")
        elif name == "TRANSCRIBING":
            self._set_status("Transcribing…")
        elif name == "UNAVAILABLE":
            pass  # status message carries the reason
        elif name in ("IDLE", "CANCELLED"):
            if not recording:
                self._voice_btn.setText("🎙")

    def set_voice_status(self, message: str) -> None:
        if message:
            self._set_status(message)

    # -- turn handling (off-thread) -------------------------------------
    def _on_send(self) -> None:
        self.submit_text(self._input.text())

    def _run_turn(self, text: str) -> None:
        self._turn_counter += 1
        self._latest_turn_id = self._turn_counter
        turn_id = self._turn_counter
        self._set_status("Thinking…")
        self._set_busy(True)

        # Cancel/replace any in-flight worker so a stale reply can't land.
        self._teardown_thread()

        self._thread = QThread(self)
        self._worker = ChatWorker(self._orchestrator, text, turn_id)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_finished(self, reply: dict, turn_id: int) -> None:
        # Revision-aware: ignore a stale reply superseded by a newer turn.
        if turn_id != self._latest_turn_id:
            return
        self._set_busy(False)
        if reply.get("needs_clarification"):
            self._append("Assistant", reply["text"])
            self._set_status("Needs clarification.")
        else:
            self._append("Assistant", reply["text"])
            src = "cloud" if reply.get("used_cloud") else "local"
            reason = reply.get("cloud_skipped_reason", "")
            self._set_status(f"Replied ({src}). {reason}".strip())
        self._sync_proposal()

    def _on_failed(self, message: str, turn_id: int) -> None:
        if turn_id != self._latest_turn_id:
            return
        self._set_busy(False)
        # Honest error; local state is preserved by the orchestrator.
        self._append("Assistant", f"Something went wrong handling that: {message}")
        self._set_status("Error — your previous state is unchanged.")
        self._sync_proposal()

    def _sync_proposal(self) -> None:
        """Keep the pending-proposal preview in sync with the LATEST revision."""
        task = self._orchestrator._engine.state.active_task()
        if task is None or not task.is_open():
            self._proposal.setVisible(False)
            return
        eff = task.effective()
        slots = eff["slots"]
        parts = []
        if slots.get("goal"):
            parts.append(f"{slots['goal'].title()}")
        if slots.get("subject"):
            parts.append(f"· {slots['subject']}")
        if slots.get("date"):
            parts.append(f"· {slots['date']}")
        if slots.get("time"):
            parts.append(f"at {slots['time']}")
        if eff["requirements"]:
            parts.append("· includes " + ", ".join(eff["requirements"]))
        detail = " ".join(parts) if parts else "(being shaped)"
        self._proposal.setText(
            f"Pending proposal (rev {eff['revision']}, {eff['status']}): {detail}"
        )
        self._proposal.setVisible(True)
        # Reveal the Confirm action only when the bridge says this proposal is a
        # schedulable reminder (explicit date + reminder intent). A casual
        # mention never shows a Confirm button.
        schedulable = bool(
            self._bridge is not None and self._bridge.active_proposal_schedulable()
        )
        self._confirm_widget.setVisible(schedulable)

    def _on_confirm_reminder(self) -> None:
        """Schedule the active proposal via the authoritative service.

        Idempotent + stale-revision-safe (guarded in the service). Disables the
        button immediately so rapid double-clicks cannot double-schedule.
        """
        if self._bridge is None:
            return
        self._confirm_btn.setEnabled(False)
        try:
            res = self._bridge.confirm_active()
        except Exception as e:  # pragma: no cover - defensive
            self._append("Assistant", f"Couldn't schedule the reminder: {e}")
            self._set_status("Scheduling failed.")
            self._confirm_btn.setEnabled(True)
            return
        if res.ok and res.reminder is not None:
            r = res.reminder
            self._append(
                "Assistant",
                f"{res.message} (reminder id {r.id})"
                + (" [already scheduled]" if res.duplicate else ""),
            )
            self._set_status("Reminder scheduled.")
            self._confirm_widget.setVisible(False)  # done; hide the action
        elif res.stale:
            # A correction landed after the button appeared; require re-confirm.
            self._append("Assistant", res.message)
            self._set_status("Please confirm the updated reminder.")
            self._confirm_btn.setEnabled(True)
        else:
            self._append("Assistant", f"Not scheduled: {res.message}")
            self._set_status("Scheduling failed.")
            self._confirm_btn.setEnabled(True)

    def _on_dismiss_reminder(self) -> None:
        self._confirm_widget.setVisible(False)
        self._set_status("Reminder not scheduled — keep revising if you like.")

    # -- helpers ---------------------------------------------------------
    def _append(self, who: str, text: str) -> None:
        self._transcript.appendPlainText(f"{who}: {text}")

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._voice_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if not busy:
            self._input.setFocus()

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(2000)
            except RuntimeError:
                pass
        self._thread = None
        self._worker = None

    # -- lifecycle -------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._teardown_thread()
        super().closeEvent(event)
        self.closed.emit()
