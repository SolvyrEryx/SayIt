# -*- coding: utf-8 -*-
"""Phase 8E Safe Zones tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.sayit.core.context.engine import ContextSignals
from src.sayit.core.safezones import is_protected, protected_match


def _sig(app="", title=""):
    return ContextSignals(app_name=app, window_title=title, detected=bool(app or title))


class TestMatching:
    def test_app_substring_match(self):
        assert protected_match(_sig(app="keepass"), ["keepass"]) == "keepass"

    def test_title_match(self):
        assert protected_match(_sig(title="1Password - Vault"), ["1password"]) == "1password"

    def test_no_match(self):
        assert protected_match(_sig(app="notepad"), ["keepass"]) is None

    def test_longest_first(self):
        # Both match "bank"; longest entry is returned deterministically.
        assert protected_match(_sig(app="mybanking"), ["bank", "banking"]) == "banking"


class TestIsProtected:
    def test_protected(self):
        r = is_protected(["keepass"], enabled=True, detector=lambda: _sig(app="keepass"))
        assert r.protected is True
        assert r.matched_entry == "keepass"

    def test_not_protected_normal_app(self):
        r = is_protected(["keepass"], enabled=True, detector=lambda: _sig(app="code"))
        assert r.protected is False

    def test_disabled_never_protected(self):
        r = is_protected(["keepass"], enabled=False, detector=lambda: _sig(app="keepass"))
        assert r.protected is False

    def test_empty_list_never_protected(self):
        r = is_protected([], enabled=True, detector=lambda: _sig(app="keepass"))
        assert r.protected is False

    def test_detection_failure_fail_safe(self):
        def boom():
            raise RuntimeError("no detection")

        r = is_protected(["keepass"], enabled=True, detector=boom)
        # Fail-safe: not protected (dictation never silently disabled by error).
        assert r.protected is False


class TestTransitions:
    def test_normal_to_protected(self):
        apps = ["keepass"]
        assert is_protected(apps, detector=lambda: _sig(app="code")).protected is False
        assert is_protected(apps, detector=lambda: _sig(app="keepass")).protected is True

    def test_protected_to_normal(self):
        apps = ["keepass"]
        assert is_protected(apps, detector=lambda: _sig(app="keepass")).protected is True
        assert is_protected(apps, detector=lambda: _sig(app="notepad")).protected is False

    def test_protected_to_protected(self):
        apps = ["keepass", "1password"]
        assert is_protected(apps, detector=lambda: _sig(app="keepass")).protected is True
        assert is_protected(apps, detector=lambda: _sig(app="1password")).protected is True

    def test_app_closed_unknown(self):
        apps = ["keepass"]
        # App closed -> empty signals -> not protected (safe default).
        assert is_protected(apps, detector=lambda: _sig()).protected is False


class TestPrivacy:
    def test_no_prohibited_imports(self):
        root = Path(__file__).resolve().parents[1]
        src = (root / "src" / "sayit" / "core" / "safezones" / "zones.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for bad in ("mss", "PIL", "pyautogui", "pyperclip"):
            assert not any(bad in (m or "") for m in imported)


class TestAppRecordingGate:
    """The Safe Zone must block recording in app._start_recording, before any
    audio is captured."""

    def test_recording_blocked_in_protected_app(self, monkeypatch, qtbot):
        import src.sayit.app as app_mod
        from src.sayit.app import AppState
        from unittest.mock import patch

        with patch.object(app_mod, "AudioRecorder") as Rec, patch.object(
            app_mod, "TranscriptionEngine"
        ), patch.object(app_mod, "HotkeyListener"), patch.object(
            app_mod, "TextOutputController"
        ), patch.object(app_mod, "SystemTray"), patch.object(
            app_mod, "RecordingToast"
        ):
            rec_instance = Rec.return_value
            rec_instance.start.return_value = True

            a = app_mod.TranscribeApp()
            a._settings.safe_zones_enabled = True
            a._settings.protected_apps = ["keepass"]

            # Force the Safe Zone check (as called in app) to report protected.
            monkeypatch.setattr(
                app_mod, "is_protected", lambda apps, enabled=True: _ProtectedResult()
            )
            a._state = AppState.IDLE
            a._start_recording()
            # Recording was gated: recorder.start must not be called.
            rec_instance.start.assert_not_called()
            assert a._state == AppState.IDLE

    def test_recording_allowed_in_normal_app(self, monkeypatch, qtbot):
        import src.sayit.app as app_mod
        from src.sayit.app import AppState
        from unittest.mock import patch

        with patch.object(app_mod, "AudioRecorder") as Rec, patch.object(
            app_mod, "TranscriptionEngine"
        ), patch.object(app_mod, "HotkeyListener"), patch.object(
            app_mod, "TextOutputController"
        ), patch.object(app_mod, "SystemTray"), patch.object(
            app_mod, "RecordingToast"
        ):
            rec_instance = Rec.return_value
            rec_instance.start.return_value = True

            a = app_mod.TranscribeApp()
            a._settings.safe_zones_enabled = True
            a._settings.protected_apps = ["keepass"]
            monkeypatch.setattr(
                app_mod, "is_protected", lambda apps, enabled=True: _NotProtectedResult()
            )
            a._state = AppState.IDLE
            a._start_recording()
            rec_instance.start.assert_called_once()


class _ProtectedResult:
    protected = True
    matched_entry = "keepass"
    app_name = "keepass"


class _NotProtectedResult:
    protected = False
    matched_entry = ""
    app_name = "code"

