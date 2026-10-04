# -*- coding: utf-8 -*-
"""Phase 8 UI tests: Snippets tab, Remember dialog, config toggles."""

from __future__ import annotations

import pytest

from src.sayit.core.settings import Settings


class TestSnippetsTab:
    def _tab(self, qtbot, settings=None):
        from src.sayit.ui.tabs.snippets_tab import SnippetsTab

        tab = SnippetsTab(settings or Settings())
        qtbot.addWidget(tab)
        return tab

    def test_add_and_save(self, qtbot):
        s = Settings()
        tab = self._tab(qtbot, s)
        tab._trigger_edit.setText("my github")
        tab._expansion_edit.setPlainText("https://github.com/me")
        tab._add_entry()
        tab.save_settings()
        assert len(s.snippets) == 1
        assert s.snippets[0]["trigger"] == "my github"
        assert s.snippets[0]["expansion"] == "https://github.com/me"

    def test_multiline_expansion_round_trip(self, qtbot):
        s = Settings()
        tab = self._tab(qtbot, s)
        tab._trigger_edit.setText("pr template")
        tab._expansion_edit.setPlainText("# Summary\n\n- item one\n- item two")
        tab._add_entry()
        tab.save_settings()
        assert "\n" in s.snippets[0]["expansion"]
        # Reload into a fresh tab preserves the multiline text.
        tab2 = self._tab(qtbot, s)
        assert len(tab2._current_snippets()) == 1
        assert "\n" in tab2._current_snippets()[0].expansion

    def test_empty_not_added(self, qtbot):
        s = Settings()
        tab = self._tab(qtbot, s)
        tab._trigger_edit.setText("x")
        tab._expansion_edit.setPlainText("")  # empty expansion
        tab._add_entry()
        tab.save_settings()
        assert s.snippets == []

    def test_load_existing(self, qtbot):
        s = Settings(snippets=[{"trigger": "a", "expansion": "b"}])
        tab = self._tab(qtbot, s)
        assert tab._table.rowCount() == 1


class TestRememberDialog:
    def test_choice_remember(self, qtbot):
        from src.sayit.ui.tabs.remember_dialog import (
            RememberChoice,
            RememberCorrectionDialog,
        )

        dlg = RememberCorrectionDialog("next j s", "Next.js")
        qtbot.addWidget(dlg)
        dlg._on_remember()
        assert dlg.choice is RememberChoice.REMEMBER

    def test_choice_never(self, qtbot):
        from src.sayit.ui.tabs.remember_dialog import (
            RememberChoice,
            RememberCorrectionDialog,
        )

        dlg = RememberCorrectionDialog("next j s", "Next.js")
        qtbot.addWidget(dlg)
        dlg._on_never()
        assert dlg.choice is RememberChoice.NEVER

    def test_choice_not_now_default(self, qtbot):
        from src.sayit.ui.tabs.remember_dialog import (
            RememberChoice,
            RememberCorrectionDialog,
        )

        dlg = RememberCorrectionDialog("next j s", "Next.js")
        qtbot.addWidget(dlg)
        assert dlg.choice is RememberChoice.NOT_NOW


class TestConfigToggles:
    def _tab(self, qtbot, settings=None):
        from src.sayit.ui.tabs.configuration_tab import ConfigurationTab

        tab = ConfigurationTab(settings or Settings())
        qtbot.addWidget(tab)
        tab.load_settings()
        return tab

    def test_intelligence_defaults(self, qtbot):
        tab = self._tab(qtbot)
        assert tab._intelligence_cb.isChecked() is True
        assert tab._voice_edit_cb.isChecked() is True
        assert tab._snippets_cb.isChecked() is True
        assert tab._structure_cb.isChecked() is True
        assert tab._developer_mode_cb.isChecked() is True

    def test_intelligence_save(self, qtbot):
        s = Settings()
        tab = self._tab(qtbot, s)
        tab._voice_edit_cb.setChecked(False)
        tab._snippets_cb.setChecked(False)
        assert tab.save_settings() is True
        assert s.voice_edit_enabled is False
        assert s.snippets_enabled is False

    def test_safe_zones_defaults(self, qtbot):
        tab = self._tab(qtbot)
        assert tab._safe_zones_cb.isChecked() is True
        assert tab._protected_list.count() == 0

    def test_safe_zones_save(self, qtbot):
        s = Settings()
        tab = self._tab(qtbot, s)
        tab._protected_list.addItem("keepass")
        tab._protected_list.addItem("1password")
        assert tab.save_settings() is True
        assert s.protected_apps == ["keepass", "1password"]

    def test_safe_zones_load_existing(self, qtbot):
        s = Settings(protected_apps=["bank"])
        tab = self._tab(qtbot, s)
        assert tab._protected_list.count() == 1
        assert tab._protected_list.item(0).text() == "bank"
