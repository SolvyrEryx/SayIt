"""Tests for the Configuration tab's Phase 6G text-correction toggles.

These verify the on-device technical-correction and structured-formatting
toggles are present, default ON, and round-trip through load/save into the
shared Settings object. They do not touch the ASR engine or the network.
"""

from src.sayit.core.settings import Settings
from src.sayit.ui.tabs.configuration_tab import ConfigurationTab


class TestCorrectionToggles:
    def test_defaults_on(self, qtbot):
        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert tab._technical_correction_cb.isChecked() is True
        assert tab._structured_formatting_cb.isChecked() is True

    def test_load_reflects_disabled(self, qtbot):
        s = Settings(
            technical_correction_enabled=False,
            structured_formatting_enabled=False,
        )
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert tab._technical_correction_cb.isChecked() is False
        assert tab._structured_formatting_cb.isChecked() is False

    def test_save_round_trip(self, qtbot):
        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()

        tab._technical_correction_cb.setChecked(False)
        tab._structured_formatting_cb.setChecked(False)
        assert tab.save_settings() is True
        assert s.technical_correction_enabled is False
        assert s.structured_formatting_enabled is False

        # Re-enable and save again to confirm both directions persist.
        tab._technical_correction_cb.setChecked(True)
        tab._structured_formatting_cb.setChecked(True)
        assert tab.save_settings() is True
        assert s.technical_correction_enabled is True
        assert s.structured_formatting_enabled is True

    def test_accessible_names_present(self, qtbot):
        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        assert tab._technical_correction_cb.accessibleName()
        assert tab._structured_formatting_cb.accessibleName()
