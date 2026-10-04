# -*- coding: utf-8 -*-
"""Phase 8 settings persistence tests."""

from __future__ import annotations

import pytest

from src.sayit.core.settings import Settings


class TestDefaults:
    def test_intelligence_defaults(self):
        s = Settings()
        assert s.intelligence_enabled is True
        assert s.voice_edit_enabled is True
        assert s.snippets_enabled is True
        assert s.structure_enabled is True
        assert s.developer_mode_enabled is True
        assert s.snippets == []
        assert s.safe_zones_enabled is True
        assert s.protected_apps == []
        assert s.correction_never_list == []
        assert s.remember_corrections_enabled is True


class TestRoundTrip:
    def test_round_trip(self, tmp_path, monkeypatch):
        import src.sayit.core.settings.settings as settings_mod

        monkeypatch.setattr(settings_mod, "get_config_dir", lambda: tmp_path)
        s = Settings(
            intelligence_enabled=False,
            voice_edit_enabled=False,
            snippets=[{"trigger": "a", "expansion": "b", "enabled": True}],
            safe_zones_enabled=True,
            protected_apps=["keepass", "bank"],
            correction_never_list=["x=>y"],
        )
        s.save()
        loaded = Settings.load()
        assert loaded.intelligence_enabled is False
        assert loaded.voice_edit_enabled is False
        assert loaded.snippets[0]["trigger"] == "a"
        assert loaded.protected_apps == ["keepass", "bank"]
        assert loaded.correction_never_list == ["x=>y"]

    def test_malformed_fields_fall_back(self, tmp_path, monkeypatch):
        import json

        import src.sayit.core.settings.settings as settings_mod

        monkeypatch.setattr(settings_mod, "get_config_dir", lambda: tmp_path)
        # Write a settings file with a malformed protected_apps.
        (tmp_path / "settings.json").write_text(
            json.dumps({"protected_apps": "not-a-list"}), encoding="utf-8"
        )
        loaded = Settings.load()
        # Falls back to the default empty list, never crashes.
        assert loaded.protected_apps == []
