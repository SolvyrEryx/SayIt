"""Persistent Voice Widget for SayIt (v0.2.0).

A small, always-on-top, frameless, draggable widget that stays available while
the user works. It provides deterministic controls over the dictation workflow
without opening the Settings window:

* a record/stop button (press to start, press again to stop) that drives the
  SAME recording path as the global hotkey;
* a Dictate-to-Note toggle (explicit opt-in routing of output into the Notes
  panel; off by default so ordinary dictation inserts into the foreground app);
* a button to show/raise the Notes panel;
* a live status label reflecting the app workflow state;
* Escape cancels the in-progress recording/transcription (same as the hotkey
  cancel), and never inserts text.

The widget is signal-based: it never touches the recorder, engine, or clipboard
itself. The app connects its signals to the existing start/stop/cancel methods,
so behaviour stays centralized and deterministic.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import ACCENT


class VoiceWidget(QWidget):
    """A persistent, draggable voice-control widget. Signal-driven."""

    record_requested = Signal()  # user asked to start recording
    stop_requested = Signal()  # user asked to stop (finish) recording
    cancel_requested = Signal()  # Escape / cancel (never inserts text)
    notes_requested = Signal()  # show/raise the Notes panel
    dictate_to_note_toggled = Signal(bool)
    moved = Signal(int, int)  # new (x, y) after a drag, for persistence

    def __init__(
        self,
        dictate_to_note: bool = False,
        position: Optional[Tuple[int, int]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self._recording = False
        self._drag_offset: Optional[QPoint] = None

        self._setup_ui(dictate_to_note)
        self._restore_position(position)

        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self._on_escape)

    def _setup_ui(self, dictate_to_note: bool) -> None:
        self.setObjectName("SayItVoiceWidget")
        self.setStyleSheet(
            """
            QWidget#SayItVoiceWidget {
                background: palette(window);
                border: 1px solid rgba(128,128,128,110);
                border-radius: 12px;
            }
            """
        )
        self.setFixedWidth(220)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        top = QHBoxLayout()
        self._status = QLabel("Ready")
        self._status.setStyleSheet("font-weight: 600;")
        top.addWidget(self._status)
        top.addStretch()
        self._grip = QLabel("⠿")
        self._grip.setStyleSheet("color: rgba(128,128,128,160);")
        self._grip.setToolTip("Drag to move")
        top.addWidget(self._grip)
        outer.addLayout(top)

        self._record_btn = QPushButton("● Record")
        self._record_btn.clicked.connect(self._on_record_clicked)
        outer.addWidget(self._record_btn)

        row = QHBoxLayout()
        self._notes_btn = QPushButton("Notes")
        self._notes_btn.clicked.connect(self.notes_requested.emit)
        row.addWidget(self._notes_btn)

        self._dtn_btn = QPushButton("→ Note")
        self._dtn_btn.setCheckable(True)
        self._dtn_btn.setChecked(dictate_to_note)
        self._dtn_btn.setToolTip(
            "Dictate-to-Note: when on, dictation is appended to the active note "
            "instead of being inserted into the foreground application."
        )
        self._dtn_btn.toggled.connect(self._on_dtn_toggled)
        row.addWidget(self._dtn_btn)
        outer.addLayout(row)

        self._apply_dtn_style(dictate_to_note)

    # -- position persistence -------------------------------------------
    def _restore_position(self, position: Optional[Tuple[int, int]]) -> None:
        if position is not None:
            self.move(int(position[0]), int(position[1]))
            return
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 24, geo.bottom() - 140)

    # -- control handlers ------------------------------------------------
    def _on_record_clicked(self) -> None:
        if self._recording:
            self.stop_requested.emit()
        else:
            self.record_requested.emit()

    def _on_dtn_toggled(self, checked: bool) -> None:
        self._apply_dtn_style(checked)
        self.dictate_to_note_toggled.emit(checked)

    def _apply_dtn_style(self, checked: bool) -> None:
        if checked:
            self._dtn_btn.setStyleSheet(
                f"QPushButton {{ background: {ACCENT}; color: white; "
                f"border-radius: 8px; }}"
            )
        else:
            self._dtn_btn.setStyleSheet("")

    def _on_escape(self) -> None:
        # Escape always requests cancel; harmless when idle (app guards it).
        self.cancel_requested.emit()

    # -- app -> widget state reflection ---------------------------------
    def set_workflow_state(self, state_name: str) -> None:
        """Reflect the app workflow state. ``state_name`` is an AppState name."""
        mapping = {
            "IDLE": ("Ready", False),
            "RECORDING": ("Recording…", True),
            "TRANSCRIBING": ("Transcribing…", False),
            "CANCELLED": ("Ready", False),
            "ERROR": ("Error", False),
        }
        label, recording = mapping.get(state_name, ("Ready", False))
        self._recording = recording
        self._status.setText(label)
        self._record_btn.setText("■ Stop" if recording else "● Record")

    def set_dictate_to_note(self, enabled: bool) -> None:
        """Set the toggle without re-emitting (used to sync from settings)."""
        self._dtn_btn.blockSignals(True)
        self._dtn_btn.setChecked(enabled)
        self._dtn_btn.blockSignals(False)
        self._apply_dtn_style(enabled)

    @property
    def dictate_to_note(self) -> bool:
        return self._dtn_btn.isChecked()

    # -- dragging --------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            pos = self.pos()
            self.moved.emit(pos.x(), pos.y())
            event.accept()
