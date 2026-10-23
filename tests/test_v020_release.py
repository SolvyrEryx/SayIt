"""Regression tests for v0.2.0 version coordination + new feature defaults."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import sayit
from sayit.core.settings.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.2.0"


def test_package_version():
    assert sayit.__version__ == EXPECTED_VERSION


def test_pyproject_project_and_briefcase_versions():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == EXPECTED_VERSION
    assert data["tool"]["briefcase"]["version"] == EXPECTED_VERSION


def test_installer_scripts_declare_version():
    for name in ("installer.iss", "installer-offline.iss"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        m = re.search(r'#define MyAppVersion "([^"]+)"', text)
        assert m is not None, f"{name} missing MyAppVersion"
        assert m.group(1) == EXPECTED_VERSION, f"{name} version drift"


def test_changelog_has_version_entry():
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{EXPECTED_VERSION}]" in text


def test_notes_and_voice_widget_defaults_off():
    """Ordinary dictation must be unchanged out of the box: all v0.2.0 UI
    features default OFF, so dictation still inserts into the foreground app."""
    s = Settings()
    assert s.notes_panel_visible is False
    assert s.voice_widget_enabled is False
    assert s.dictate_to_note_enabled is False
    assert s.voice_widget_position is None


def test_new_settings_persist_round_trip(tmp_path, monkeypatch):
    import sayit.core.settings.settings as st

    monkeypatch.setattr(st, "get_config_dir", lambda: tmp_path)
    # default enhancements lookup touches llm; stub to keep this unit-focused
    monkeypatch.setattr(st, "_get_default_enhancements", lambda: [])

    s = Settings()
    s.dictate_to_note_enabled = True
    s.voice_widget_enabled = True
    s.voice_widget_position = (12, 34)
    s.save()

    loaded = Settings.load()
    assert loaded.dictate_to_note_enabled is True
    assert loaded.voice_widget_enabled is True
    assert tuple(loaded.voice_widget_position) == (12, 34)


def test_notes_dock_side_default_and_validation():
    from sayit.core.settings.settings import Settings

    s = Settings()
    assert s.notes_dock_side == "right"  # default
    # Invalid stored values fall back to "right" (safe-by-default).
    assert Settings(notes_dock_side="sideways").notes_dock_side == "right"
    assert Settings(notes_dock_side="left").notes_dock_side == "left"


def test_notes_dock_side_persists_round_trip(tmp_path, monkeypatch):
    import sayit.core.settings.settings as st
    from sayit.core.settings.settings import Settings

    monkeypatch.setattr(st, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(st, "_get_default_enhancements", lambda: [])
    s = Settings()
    s.notes_dock_side = "left"
    s.save()
    assert Settings.load().notes_dock_side == "left"
