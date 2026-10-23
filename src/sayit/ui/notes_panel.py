"""Standalone, docked Notes panel for SayIt (v0.2.0).

A small top-level window holding one or more local notes. It:

* edits the active note from a local :class:`NotesStore` (on-device JSON);
* autosaves on a short (500 ms) debounce after edits and on close/hide, so
  notes survive a restart or crash;
* provides a "New note" button that creates + selects a fresh note while
  preserving the current note's unsaved edits (they are flushed first);
* docks to a configurable screen edge (left/right, right by default), clamped
  to the screen's available work area with off-screen recovery;
* animates in with a ~200 ms edge slide, honouring reduced-motion;
* exposes :meth:`append_dictation` so the app can route a dictated transcript
  into the active note when Dictate-to-Note is enabled.

It is intentionally independent of the Settings dialog so it can stay open as a
scratchpad while the user works in other applications. Presentation-only: it
never touches the recorder, engine, or clipboard.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __display_name__
from ..core.notes import NotesStore
from . import motion
from .theme import STYLESHEET

# Debounce for autosave after the user stops typing (ms). ~500 ms per spec:
# short enough that a surprise crash loses at most half a second of edits, long
# enough to avoid writing on every keystroke.
_AUTOSAVE_DEBOUNCE_MS = 500


class NotesPanel(QWidget):
    """A standalone docked notes scratchpad backed by a local NotesStore."""

    # Emitted after the panel hides/closes so the app can sync settings/UI.
    closed = Signal()

    def __init__(
        self,
        store: Optional[NotesStore] = None,
        parent: Optional[QWidget] = None,
        dock_side: str = "right",
    ):
        # Top-level tool window: stays out of the taskbar, above normal windows,
        # but is NOT a modal dialog so the user keeps working elsewhere.
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self._store = store or NotesStore()
        self._dock_side = dock_side if dock_side in ("left", "right") else "right"

        self.setWindowTitle(f"{__display_name__} — Notes")
        self.setMinimumWidth(320)
        self.setMinimumHeight(360)
        # Follow the app theme (palette-based; coexists with light/dark).
        self.setStyleSheet(STYLESHEET)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(_AUTOSAVE_DEBOUNCE_MS)
        self._autosave_timer.timeout.connect(self._flush_autosave)

        self._setup_ui()
        self._load_from_store()
        self.dock_to_edge(self._dock_side)

    # -- UI --------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setObjectName("SayItNotesPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        header = QHBoxLayout()
        title = QLabel("Notes")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self._status = QLabel("Saved")
        self._status.setStyleSheet("color: rgba(128,128,128,200); font-size: 11px;")
        header.addWidget(self._status)
        layout.addLayout(header)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "Type here, or enable Dictate-to-Note and speak to append."
        )
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        row = QHBoxLayout()
        self._new_btn = QPushButton("New note")
        self._new_btn.setToolTip(
            "Create a new note. Your current note and its unsaved edits are kept."
        )
        self._new_btn.clicked.connect(self.new_note)
        row.addWidget(self._new_btn)
        row.addStretch()
        self._save_btn = QPushButton("Save now")
        self._save_btn.clicked.connect(self._flush_autosave)
        row.addWidget(self._save_btn)
        layout.addLayout(row)

        # Esc closes (and autosaves) the panel deterministically.
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.close)

    # -- docking ---------------------------------------------------------
    def dock_to_edge(self, side: Optional[str] = None) -> None:
        """Dock to the given edge within the current screen's work area.

        Clamps fully inside ``availableGeometry`` (off-screen recovery) and is
        multi-monitor safe: it uses the screen under the panel's current center
        when one exists, else the primary screen.
        """
        if side is not None:
            self._dock_side = side if side in ("left", "right") else "right"

        screen = self._current_screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = max(self.minimumWidth(), 360)
        h = min(int(geo.height() * 0.8), geo.height())
        y = geo.top() + max(0, int(geo.height() * 0.1))
        # Keep the panel fully within the vertical work area.
        if y + h > geo.bottom():
            y = max(geo.top(), geo.bottom() - h)

        if self._dock_side == "left":
            x = geo.left() + 8
        else:
            x = geo.right() - w - 8
        # Horizontal off-screen recovery / clamp.
        x = max(geo.left(), min(x, geo.right() - w))

        self.setGeometry(x, y, w, h)

    def _current_screen(self):
        try:
            center = self.frameGeometry().center()
            scr = QGuiApplication.screenAt(center)
            if scr is not None:
                return scr
        except RuntimeError:
            pass
        return QGuiApplication.primaryScreen()

    @property
    def dock_side(self) -> str:
        return self._dock_side

    def show_docked(self) -> None:
        """Dock + reveal with a reduced-motion-aware edge slide (~200 ms)."""
        self.dock_to_edge(self._dock_side)
        motion.slide_in_from_edge(self, side=self._dock_side)

    # -- store binding ---------------------------------------------------
    def _load_from_store(self) -> None:
        self._suppress_change = True
        try:
            self._editor.setPlainText(self._store.get_active_content())
        finally:
            self._suppress_change = False
        self._update_status(saved=True)

    def _on_text_changed(self) -> None:
        if getattr(self, "_suppress_change", False):
            return
        self._store.set_active_content(self._editor.toPlainText())
        self._update_status(saved=False)
        self._autosave_timer.start()

    def _flush_autosave(self) -> None:
        self._autosave_timer.stop()
        try:
            self._store.save()
            self._update_status(saved=True)
        except OSError:
            self._update_status(saved=False, error=True)

    def _update_status(self, *, saved: bool, error: bool = False) -> None:
        if error:
            self._status.setText("Save failed")
        elif saved:
            self._status.setText("Saved")
        else:
            self._status.setText("Unsaved…")

    # -- public API ------------------------------------------------------
    @property
    def store(self) -> NotesStore:
        return self._store

    def new_note(self) -> None:
        """Create + select a new note, preserving the current note's edits.

        The current (possibly unsaved) edits are flushed to disk first so they
        are never lost, then a fresh empty note becomes active and is persisted.
        """
        # 1) Persist whatever is currently being edited (non-destructive).
        self._store.set_active_content(self._editor.toPlainText())
        try:
            self._store.save()
        except OSError:
            self._update_status(saved=False, error=True)
            # Do not switch notes if we could not protect the current edits.
            return
        # 2) Create + select the new (empty) note and persist the selection.
        self._store.create_note()
        try:
            self._store.save()
        except OSError:
            self._update_status(saved=False, error=True)
        # 3) Reflect the new empty note in the editor.
        self._load_from_store()

    def append_dictation(self, text: str) -> None:
        """Append a dictated transcript into the active note and persist it.

        Called by the app when Dictate-to-Note routing is active. Updates the
        editor (preserving the caret at the end) and saves immediately so a
        spoken note is never lost.
        """
        if not text:
            return
        new_content = self._store.append_to_active(text)
        self._suppress_change = True
        try:
            self._editor.setPlainText(new_content)
            cursor = self._editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)
            self._editor.ensureCursorVisible()
        finally:
            self._suppress_change = False
        self._flush_autosave()

    def focus_editor(self) -> None:
        self._editor.setFocus()

    # -- lifecycle -------------------------------------------------------
    def closeEvent(self, event) -> None:
        # Always autosave on close so no edits are lost.
        self._flush_autosave()
        super().closeEvent(event)
        self.closed.emit()

    def hideEvent(self, event) -> None:
        self._flush_autosave()
        super().hideEvent(event)
