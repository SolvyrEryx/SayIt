"""Central motion system for SayIt.

A small, dependency-free layer over Qt's native animation primitives. It
centralizes durations and easing, honours a reduced-motion preference, and
provides lifecycle-safe fade helpers so individual widgets don't hand-roll
animation values or leak animation objects.

Design rules:
- Presentational only. Nothing here touches application state or workflow.
- Reduced motion: when enabled, animations become near-instant (the final
  visual state is applied immediately) so behavior never depends on motion.
- Safety: helpers tolerate widgets that are hidden/deleted, stop any prior
  animation they own, and keep a reference on the target so the QPropertyAnimation
  is not garbage-collected mid-flight.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

# --- Durations (ms) -------------------------------------------------------
FAST = 120
NORMAL = 180
MEDIUM = 240
SLOW = 320

# --- Easing ---------------------------------------------------------------
EASE_OUT = QEasingCurve.OutCubic      # elements entering
EASE_IN_OUT = QEasingCurve.InOutCubic  # transitions
EASE_IN = QEasingCurve.InCubic        # elements leaving


def reduced_motion() -> bool:
    """Return True if animations should be skipped / made instant.

    Honours the ``SAYIT_REDUCED_MOTION`` environment variable (set to "1" to
    force reduced motion, useful for tests and users). Qt does not expose a
    cross-platform reduced-motion flag, so this env var is the explicit opt-in;
    the default is normal motion.
    """
    return os.environ.get("SAYIT_REDUCED_MOTION", "") == "1"


def _opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """Get or create an opacity effect for a widget, reusing an existing one."""
    eff = widget.graphicsEffect()
    if isinstance(eff, QGraphicsOpacityEffect):
        return eff
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    return eff


def _is_alive(widget: Optional[QWidget]) -> bool:
    try:
        # Accessing a method on a deleted QObject raises RuntimeError.
        return widget is not None and widget.parent() is not None or (
            widget is not None and widget.isWidgetType()
        )
    except RuntimeError:
        return False


def fade_in(
    widget: QWidget,
    duration: int = NORMAL,
    on_finished: Optional[Callable[[], None]] = None,
) -> None:
    """Fade a widget from transparent to opaque. Instant under reduced motion."""
    if widget is None:
        return
    if reduced_motion():
        widget.show()
        _clear_effect(widget)
        if on_finished:
            on_finished()
        return

    eff = _opacity_effect(widget)
    eff.setOpacity(0.0)
    widget.show()
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASE_OUT)

    def _done():
        _clear_effect(widget)
        if on_finished:
            on_finished()

    anim.finished.connect(_done)
    _retain(widget, anim)
    anim.start()


def fade_out(
    widget: QWidget,
    duration: int = FAST,
    on_finished: Optional[Callable[[], None]] = None,
) -> None:
    """Fade a widget to transparent. Instant under reduced motion."""
    if widget is None:
        return
    if reduced_motion():
        if on_finished:
            on_finished()
        return

    eff = _opacity_effect(widget)
    eff.setOpacity(1.0)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(EASE_IN)
    if on_finished:
        anim.finished.connect(on_finished)
    _retain(widget, anim)
    anim.start()


def crossfade_text(label, new_text: str, duration: int = FAST) -> None:
    """Swap a QLabel's text with a quick fade-out/in. Instant under reduced motion.

    Safe to call repeatedly; it replaces any prior crossfade on the label.
    """
    if label is None:
        return
    if label.text() == new_text:
        return
    if reduced_motion():
        label.setText(new_text)
        _clear_effect(label)
        return

    def _swap():
        try:
            label.setText(new_text)
        except RuntimeError:
            return
        fade_in(label, duration)

    fade_out(label, duration, on_finished=_swap)


def _clear_effect(widget: QWidget) -> None:
    """Remove the opacity effect so the widget paints normally afterward."""
    try:
        widget.setGraphicsEffect(None)
    except RuntimeError:
        pass


def _retain(owner: QObject, anim) -> None:
    """Keep a reference to the running animation on its owner.

    Stops/replaces any previous animation this helper stored on the same owner
    so animations don't accumulate or fight over the same property. The
    animation is parented to the target widget, so it is destroyed with it.
    """
    try:
        prev = owner.property("_sayit_anim")
    except RuntimeError:
        return
    if isinstance(prev, (QPropertyAnimation, QParallelAnimationGroup)):
        try:
            prev.stop()
        except RuntimeError:
            pass
    owner.setProperty("_sayit_anim", anim)


# Default vertical travel for entrance animations (px).
SLIDE_DISTANCE = 10


def slide_up_in(
    widget: QWidget,
    distance: int = SLIDE_DISTANCE,
    duration: int = MEDIUM,
    delay: int = 0,
) -> None:
    """Fade a widget in while it rises a few px into place.

    Instant under reduced motion. ``delay`` (ms) lets callers stagger several
    widgets. Lifecycle-safe: animations are parented to the widget and replace
    any prior entrance animation on it.
    """
    if widget is None:
        return
    if reduced_motion():
        widget.show()
        _clear_effect(widget)
        return

    def _run():
        try:
            if not widget.isWidgetType():
                return
        except RuntimeError:
            return
        eff = _opacity_effect(widget)
        eff.setOpacity(0.0)
        widget.show()
        start_pos = widget.pos()

        group = QParallelAnimationGroup(widget)

        op = QPropertyAnimation(eff, b"opacity", widget)
        op.setDuration(duration)
        op.setStartValue(0.0)
        op.setEndValue(1.0)
        op.setEasingCurve(EASE_OUT)
        group.addAnimation(op)

        pos = QPropertyAnimation(widget, b"pos", widget)
        pos.setDuration(duration)
        pos.setStartValue(QPoint(start_pos.x(), start_pos.y() + distance))
        pos.setEndValue(start_pos)
        pos.setEasingCurve(EASE_OUT)
        group.addAnimation(pos)

        group.finished.connect(lambda: _clear_effect(widget))
        _retain(widget, group)
        group.start()

    if delay > 0:
        QTimer.singleShot(delay, _run)
    else:
        _run()


def stagger(widgets, base: int = 0, step: int = 20, cap: int = 80, **kwargs) -> None:
    """Entrance-animate several widgets with a tiny cumulative stagger.

    The per-item delay is clamped so the total stays small (<= ``cap`` ms) to
    avoid a "marketing webpage" cascade. Each widget uses ``slide_up_in``.
    """
    for i, w in enumerate(widgets):
        delay = min(base + i * step, cap)
        slide_up_in(w, delay=delay, **kwargs)


def animate_height(widget: QWidget, expand: bool, duration: int = NORMAL) -> None:
    """Expand/collapse a widget by animating its maximum height (accordion).

    When expanding, the natural sizeHint height is the target; collapsing goes
    to 0. Instant under reduced motion. Safe to call rapidly — any in-flight
    height animation on the widget is replaced.
    """
    if widget is None:
        return

    if reduced_motion():
        widget.setMaximumHeight(16777215 if expand else 0)
        widget.setVisible(expand)
        return

    if expand:
        widget.setVisible(True)
        target = max(widget.sizeHint().height(), 0)
        start = widget.maximumHeight() if widget.maximumHeight() < target else 0
        anim = QPropertyAnimation(widget, b"maximumHeight", widget)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(EASE_OUT)

        def _done_expand():
            # Release the cap so the widget can resize normally afterward.
            try:
                widget.setMaximumHeight(16777215)
            except RuntimeError:
                pass

        anim.finished.connect(_done_expand)
        _retain(widget, anim)
        anim.start()
    else:
        start = widget.height()
        anim = QPropertyAnimation(widget, b"maximumHeight", widget)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(0)
        anim.setEasingCurve(EASE_IN)
        anim.finished.connect(lambda: widget.setVisible(False))
        _retain(widget, anim)
        anim.start()
