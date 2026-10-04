"""Shared visual theme for SayIt.

Provides:
- ``sayit_mark()``: a simple, code-drawn vector mark (a microphone capsule with
  an audio-waveform motif) returned as a QPixmap/QIcon. No external image asset
  is used — the mark is painted so it scales cleanly for the tray, window
  header, and future icon use.
- ``STYLESHEET``: a calm, neutral Qt stylesheet with restrained spacing,
  typography, and subtle borders. It uses the palette's own colors where
  possible so it reads reasonably in both light and dark system themes.

This module is presentation-only. It does not change application behavior.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

# Restrained accent used for interactive/recording emphasis. A quiet teal rather
# than a neon "AI" color.
ACCENT = "#3B9C8C"
ACCENT_RECORDING = "#D9534F"  # calm red, used only for the active-recording state


def sayit_mark(size: int = 64, color: str = "#2E2E2E") -> QPixmap:
    """Return a square QPixmap with the SayIt microphone + waveform mark.

    The mark is a rounded microphone capsule flanked by a few waveform bars. It
    is intentionally minimal and monochrome so it works at small sizes and on
    any background.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    c = QColor(color)
    s = size

    # Microphone capsule (centered vertical rounded rect).
    cap_w = s * 0.26
    cap_h = s * 0.46
    cap_x = (s - cap_w) / 2
    cap_y = s * 0.14
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawRoundedRect(cap_x, cap_y, cap_w, cap_h, cap_w / 2, cap_w / 2)

    # Mic stand + base.
    pen = QPen(c, max(1.5, s * 0.035))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    stand_top = cap_y + cap_h + s * 0.02
    stand_bottom = s * 0.80
    center_x = s / 2
    # Cradle arc under the capsule.
    arc_r = cap_w * 1.15
    p.drawArc(
        int(center_x - arc_r),
        int(cap_y + cap_h - arc_r * 0.6),
        int(arc_r * 2),
        int(arc_r * 1.2),
        200 * 16,
        140 * 16,
    )
    p.drawLine(QPointF(center_x, stand_top), QPointF(center_x, stand_bottom))
    p.drawLine(
        QPointF(center_x - s * 0.12, stand_bottom),
        QPointF(center_x + s * 0.12, stand_bottom),
    )

    # Waveform bars flanking the capsule (the "voice" motif).
    bar_w = max(1.5, s * 0.03)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    heights = [0.14, 0.24, 0.18]
    for i, h in enumerate(heights):
        bh = s * h
        y = (s * 0.40) - bh / 2
        left_x = cap_x - s * 0.08 - i * (bar_w + s * 0.035)
        right_x = cap_x + cap_w + s * 0.08 + i * (bar_w + s * 0.035)
        p.drawRoundedRect(left_x, y, bar_w, bh, bar_w / 2, bar_w / 2)
        p.drawRoundedRect(right_x, y, bar_w, bh, bar_w / 2, bar_w / 2)

    p.end()
    return pm


def sayit_icon(size: int = 64, color: str = "#2E2E2E") -> QIcon:
    return QIcon(sayit_mark(size, color))


# Calm, neutral stylesheet. Deliberately light-touch: it sets spacing,
# radii, and restrained borders/typography without hard-coding a full dark/light
# palette, so it coexists with the system theme and the overlay's own styling.
STYLESHEET = """
QWidget {
    font-size: 13px;
}
QDialog, QWidget#SayItMainWindow {
    /* leave background to the platform palette for light/dark friendliness */
}
QGroupBox {
    border: 1px solid rgba(128, 128, 128, 60);
    border-radius: 10px;
    margin-top: 14px;
    padding: 10px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    border: 1px solid rgba(128, 128, 128, 70);
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover {
    border-color: rgba(59, 156, 140, 160);
}
QPushButton:pressed {
    background: rgba(59, 156, 140, 30);
}
QPushButton:focus {
    border: 2px solid #3B9C8C;
    outline: none;
}
QPushButton:disabled {
    color: rgba(128, 128, 128, 160);
}
QComboBox, QLineEdit, QKeySequenceEdit {
    border: 1px solid rgba(128, 128, 128, 70);
    border-radius: 8px;
    padding: 5px 8px;
    min-height: 20px;
}
QComboBox:focus, QLineEdit:focus {
    border: 2px solid #3B9C8C;
}
QListWidget {
    border: none;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 8px;
}
QListWidget::item:selected {
    background: rgba(59, 156, 140, 45);
    color: palette(text);
}
QProgressBar {
    border: 1px solid rgba(128, 128, 128, 70);
    border-radius: 6px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #3B9C8C;
    border-radius: 5px;
}
"""
