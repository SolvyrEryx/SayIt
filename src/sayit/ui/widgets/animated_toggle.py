"""An accessible animated on/off switch.

A checkable QAbstractButton with a thumb that slides between off/on positions.
It is keyboard-focusable and reports its checked state like a checkbox, so it
remains accessible. Under reduced motion the thumb jumps instantly.

Presentation-only: it is a drop-in boolean control; callers read/set
``isChecked()`` exactly as with a QCheckBox.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton

from ..motion import FAST, reduced_motion

_OFF_COLOR = QColor("#B8B8B8")
_ON_COLOR = QColor("#3B9C8C")
_THUMB_COLOR = QColor("#FFFFFF")


class AnimatedToggle(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._track_w = 40
        self._track_h = 22
        self._margin = 3
        self.setFixedSize(self._track_w, self._track_h)
        # 0.0 = off (left), 1.0 = on (right).
        self._pos = 0.0
        self.toggled.connect(self._on_toggled)

    # Animated thumb position as a Qt property so QPropertyAnimation can drive it.
    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, value: float) -> None:
        self._pos = value
        self.update()

    thumbPos = Property(float, _get_pos, _set_pos)

    def sizeHint(self) -> QSize:
        return QSize(self._track_w, self._track_h)

    def _on_toggled(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if reduced_motion():
            self._set_pos(target)
            return
        anim = QPropertyAnimation(self, b"thumbPos", self)
        anim.setDuration(FAST)
        anim.setStartValue(self._pos)
        anim.setEndValue(target)
        prev = self.property("_toggle_anim")
        if isinstance(prev, QPropertyAnimation):
            prev.stop()
        self.setProperty("_toggle_anim", anim)
        anim.start()

    def setChecked(self, checked: bool) -> None:  # keep thumb in sync for programmatic sets
        super().setChecked(checked)
        self._set_pos(1.0 if checked else 0.0)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Track: blend off->on color by position.
        off, on = _OFF_COLOR, _ON_COLOR
        t = self._pos
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        radius = self._track_h / 2
        p.drawRoundedRect(0, 0, self._track_w, self._track_h, radius, radius)

        # Thumb.
        thumb_d = self._track_h - 2 * self._margin
        x0 = self._margin
        x1 = self._track_w - self._margin - thumb_d
        x = x0 + (x1 - x0) * self._pos
        p.setBrush(_THUMB_COLOR)
        p.drawEllipse(int(x), self._margin, int(thumb_d), int(thumb_d))

        # Visible focus ring for keyboard accessibility.
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            pen = p.pen()
            pen.setColor(_ON_COLOR)
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRoundedRect(1, 1, self._track_w - 2, self._track_h - 2, radius, radius)

        p.end()
