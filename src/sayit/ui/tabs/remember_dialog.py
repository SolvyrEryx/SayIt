"""Phase 8F "Remember this correction?" prompt dialog.

A small, explicit, reversible prompt. It is only ever shown in response to a
user-provided correction; it never pops up from passive observation. The three
outcomes map to the deterministic learning policy:

    Remember -> create a 6J vocabulary entry
    Not now  -> do nothing
    Never    -> suppress this exact candidate in future

The dialog itself performs no learning; it only reports the user's choice.
"""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RememberChoice(Enum):
    REMEMBER = auto()
    NOT_NOW = auto()
    NEVER = auto()


class RememberCorrectionDialog(QDialog):
    def __init__(self, spoken: str, written: str, parent: QWidget = None):
        super().__init__(parent)
        self._choice = RememberChoice.NOT_NOW
        self.setWindowTitle("Remember this correction?")
        self.setModal(True)
        self._build(spoken, written)

    def _build(self, spoken: str, written: str) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Remember this correction?")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        title.setAccessibleName("Remember this correction")
        layout.addWidget(title)

        mapping = QLabel(f'"{spoken}"  \u2192  "{written}"')
        mapping.setStyleSheet("font-size: 14px;")
        mapping.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(mapping)

        hint = QLabel(
            "This adds a local vocabulary rule you can edit or delete anytime "
            "in the Vocabulary tab. Nothing is sent anywhere."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        never_btn = QPushButton("Never")
        never_btn.setAccessibleName("Never remember this correction")
        never_btn.clicked.connect(self._on_never)
        buttons.addWidget(never_btn)

        buttons.addStretch()

        not_now_btn = QPushButton("Not now")
        not_now_btn.setAccessibleName("Do not remember now")
        not_now_btn.clicked.connect(self._on_not_now)
        buttons.addWidget(not_now_btn)

        remember_btn = QPushButton("Remember")
        remember_btn.setDefault(True)
        remember_btn.setAccessibleName("Remember this correction")
        remember_btn.clicked.connect(self._on_remember)
        buttons.addWidget(remember_btn)

        layout.addLayout(buttons)

    @property
    def choice(self) -> RememberChoice:
        return self._choice

    def _on_remember(self) -> None:
        self._choice = RememberChoice.REMEMBER
        self.accept()

    def _on_not_now(self) -> None:
        self._choice = RememberChoice.NOT_NOW
        self.reject()

    def _on_never(self) -> None:
        self._choice = RememberChoice.NEVER
        self.reject()
