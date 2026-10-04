"""Tests for the motion layer and animated navigation.

Motion is forced to reduced (instant) mode in tests via conftest, so these
tests are deterministic and do not depend on animation timing.
"""

import os

from unittest.mock import patch

from PySide6.QtWidgets import QLabel

from src.sayit.ui import motion


class TestMotionReducedMode:
    def test_reduced_motion_env(self):
        # conftest sets SAYIT_REDUCED_MOTION=1 for the test session.
        assert os.environ.get("SAYIT_REDUCED_MOTION") == "1"
        assert motion.reduced_motion() is True

    def test_crossfade_instant_under_reduced_motion(self, qtbot):
        lbl = QLabel("Ready to speak")
        qtbot.addWidget(lbl)
        motion.crossfade_text(lbl, "Listening…")
        # Reduced motion applies the final text synchronously.
        assert lbl.text() == "Listening…"

    def test_fade_in_shows_widget_instantly(self, qtbot):
        lbl = QLabel("x")
        qtbot.addWidget(lbl)
        lbl.hide()
        motion.fade_in(lbl)
        assert lbl.isHidden() is False

    def test_helpers_tolerate_none(self):
        # Must not raise on None.
        motion.fade_in(None)
        motion.fade_out(None)
        motion.crossfade_text(None, "x")

    def test_crossfade_noop_when_same_text(self, qtbot):
        lbl = QLabel("same")
        qtbot.addWidget(lbl)
        motion.crossfade_text(lbl, "same")
        assert lbl.text() == "same"


class TestMotionNormalMode:
    def test_crossfade_schedules_without_crash(self, qtbot):
        # Temporarily disable reduced motion to exercise the animated path.
        with patch.object(motion, "reduced_motion", return_value=False):
            lbl = QLabel("a")
            qtbot.addWidget(lbl)
            lbl.show()
            motion.crossfade_text(lbl, "b")  # should not raise
            motion.fade_in(lbl)
            motion.fade_out(lbl)


class TestAnimatedNavigation:
    def test_tab_switch_no_crash_no_duplicate_widgets(self, qtbot):
        from src.sayit.core.settings import Settings
        from src.sayit.ui.main_window import SettingsWindow

        with patch("src.sayit.ui.main_window.get_settings", return_value=Settings()):
            win = SettingsWindow()
            qtbot.addWidget(win)

            count_before = win._stacked.count()
            n = win._nav_list.count()
            # Switch across every tab, twice.
            for _ in range(2):
                for row in range(n):
                    win._nav_list.setCurrentRow(row)
            # No widgets were added/removed by switching.
            assert win._stacked.count() == count_before
            # Current widget matches the selected row.
            assert win._stacked.currentIndex() == win._nav_list.currentRow()


class TestNewMotionHelpers:
    def test_slide_up_in_instant_under_reduced_motion(self, qtbot):
        lbl = QLabel("x")
        qtbot.addWidget(lbl)
        lbl.hide()
        motion.slide_up_in(lbl)
        assert lbl.isHidden() is False

    def test_stagger_tolerates_many_and_none(self, qtbot):
        widgets = [QLabel(str(i)) for i in range(5)]
        for w in widgets:
            qtbot.addWidget(w)
        motion.stagger(widgets)  # must not raise
        motion.stagger([])  # empty is fine

    def test_animate_height_expand_collapse_reduced(self, qtbot):
        from PySide6.QtWidgets import QWidget

        box = QWidget()
        qtbot.addWidget(box)
        motion.animate_height(box, expand=True)
        assert box.isHidden() is False
        motion.animate_height(box, expand=False)
        # Collapsed is instant under reduced motion.
        assert box.isHidden() is True

    def test_animate_height_rapid_toggle_no_crash(self, qtbot):
        from PySide6.QtWidgets import QWidget

        box = QWidget()
        qtbot.addWidget(box)
        with patch.object(motion, "reduced_motion", return_value=False):
            for _ in range(6):
                motion.animate_height(box, expand=True)
                motion.animate_height(box, expand=False)
        # No exception, box still a valid widget.
        assert box is not None


class TestAnimatedToggle:
    def test_checkable_and_syncs(self, qtbot):
        from src.sayit.ui.widgets import AnimatedToggle

        t = AnimatedToggle()
        qtbot.addWidget(t)
        assert t.isCheckable() is True
        assert t.isChecked() is False
        t.setChecked(True)
        assert t.isChecked() is True
        assert t._pos == 1.0  # thumb synced for programmatic set
        t.setChecked(False)
        assert t.isChecked() is False
        assert t._pos == 0.0

    def test_animates_without_crash_normal_mode(self, qtbot):
        from src.sayit.ui.widgets import AnimatedToggle

        with patch.object(motion, "reduced_motion", return_value=False):
            t = AnimatedToggle()
            qtbot.addWidget(t)
            t.toggle()  # triggers animated path
            t.toggle()
            assert t is not None

    def test_accessible_name(self, qtbot):
        from src.sayit.ui.widgets import AnimatedToggle

        t = AnimatedToggle()
        qtbot.addWidget(t)
        t.setAccessibleName("Save transcript history")
        assert t.accessibleName() == "Save transcript history"


class TestDialogLifecycle:
    def test_download_dialog_show_close_no_crash(self, qtbot):
        from src.sayit.ui.download_dialog import DownloadDialog

        d = DownloadDialog("sherpa-onnx-whisper-tiny")
        qtbot.addWidget(d)
        d.show()
        d.close()
        assert d is not None
