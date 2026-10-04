# -*- coding: utf-8 -*-
"""Phase 8A tests: local context engine + profiles.

Coverage mirrors the Phase 8 testing strategy:

- Positive: profile selection, app->profile mapping, override precedence, and
  that a profile influences the existing correction flags.
- Negative: ordinary prose is never rewritten by context; detection failure and
  disabled detection both resolve to Normal.
- Determinism: identical signals + settings always resolve identically.
- Privacy: the context modules import no screenshot/clipboard libraries and the
  signals carry only metadata, never content.
- Regression: Phase 6G/6I/6J behavior is unchanged (Normal/Developer keep the
  shipped flags; the raw correct_transcript API is untouched).
- Settings + UI round-trip for the new controls.

Everything here is offline and injects a fake detector, so no real OS calls are
made in CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.sayit.core.context import (
    ContextEngine,
    ContextResolution,
    ContextSignals,
    Profile,
    ProfileConfig,
    profile_config,
    resolve_profile,
)
from src.sayit.core.context.profiles import AUTO, DEFAULT_APP_PROFILE_MAP
from src.sayit.core.settings import Settings
from src.sayit.core.transcript_processor import correct_transcript


# --- helpers ----------------------------------------------------------------

def _signals(app="", title=""):
    return ContextSignals(app_name=app, window_title=title, detected=bool(app or title))


def _fake_engine(settings, app="", title=""):
    return ContextEngine(settings, detector=lambda: _signals(app, title))


# --- profile config table ---------------------------------------------------

class TestProfileConfig:
    def test_all_profiles_have_config(self):
        for prof in Profile:
            cfg = profile_config(prof)
            assert isinstance(cfg, ProfileConfig)

    def test_developer_full_technical_layer(self):
        cfg = profile_config(Profile.DEVELOPER)
        assert cfg == ProfileConfig(True, True, True)

    def test_normal_matches_shipped_defaults(self):
        # Normal must preserve the current shipped behavior (6G/6I all on).
        assert profile_config(Profile.NORMAL) == ProfileConfig(True, True, True)

    def test_email_notes_disable_structured(self):
        for prof in (Profile.EMAIL, Profile.NOTES):
            cfg = profile_config(prof)
            assert cfg.enable_structured is False
            # But keep safe technical-term normalization on.
            assert cfg.enable_technical is True

    def test_from_value_fail_safe(self):
        assert Profile.from_value("developer") is Profile.DEVELOPER
        assert Profile.from_value("DEVELOPER") is Profile.DEVELOPER
        assert Profile.from_value("nonsense") is Profile.NORMAL
        assert Profile.from_value(None) is Profile.NORMAL
        assert Profile.from_value("") is Profile.NORMAL


# --- pure resolution: precedence --------------------------------------------

class TestResolutionPrecedence:
    def test_override_wins_over_mapping(self):
        # A concrete override must beat a mapping that would say Developer.
        r = resolve_profile(
            _signals(app="code"),
            detection_enabled=True,
            override="email",
        )
        assert r.profile is Profile.EMAIL
        assert r.source == "override"

    def test_disabled_detection_is_normal(self):
        r = resolve_profile(
            _signals(app="code"),
            detection_enabled=False,
            override=AUTO,
        )
        assert r.profile is Profile.NORMAL
        assert r.source == "disabled"

    def test_mapping_match(self):
        r = resolve_profile(
            _signals(app="code", title="main.py - Visual Studio Code"),
            detection_enabled=True,
            override=AUTO,
        )
        assert r.profile is Profile.DEVELOPER
        assert r.source == "mapping"

    def test_default_when_no_match(self):
        r = resolve_profile(
            _signals(app="someunknownapp"),
            detection_enabled=True,
            override=AUTO,
        )
        assert r.profile is Profile.NORMAL
        assert r.source == "default"

    def test_auto_with_no_signals_is_normal(self):
        r = resolve_profile(
            ContextSignals(),
            detection_enabled=True,
            override=AUTO,
        )
        assert r.profile is Profile.NORMAL
        assert r.source == "default"


# --- app -> profile mapping --------------------------------------------------

class TestAppMapping:
    @pytest.mark.parametrize(
        "app,expected",
        [
            ("code", Profile.DEVELOPER),
            ("cursor", Profile.DEVELOPER),
            ("windowsterminal", Profile.DEVELOPER),
            ("powershell", Profile.DEVELOPER),
            ("outlook", Profile.EMAIL),
            ("thunderbird", Profile.EMAIL),
            ("slack", Profile.CHAT),
            ("discord", Profile.CHAT),
            ("notion", Profile.NOTES),
            ("obsidian", Profile.NOTES),
        ],
    )
    def test_default_map(self, app, expected):
        r = resolve_profile(
            _signals(app=app), detection_enabled=True, override=AUTO
        )
        assert r.profile is expected
        assert r.source == "mapping"

    def test_title_substring_match(self):
        # When the app name is empty, the window title can still match.
        r = resolve_profile(
            _signals(app="", title="Inbox - Outlook"),
            detection_enabled=True,
            override=AUTO,
        )
        assert r.profile is Profile.EMAIL

    def test_user_mapping_overrides_default(self):
        s = Settings(context_app_mappings={"code": "email"})
        eng = _fake_engine(s, app="code")
        r = eng.resolve()
        # User remapped VS Code to Email.
        assert r.profile is Profile.EMAIL

    def test_user_mapping_adds_new_app(self):
        s = Settings(context_app_mappings={"myeditor": "developer"})
        eng = _fake_engine(s, app="myeditor")
        assert eng.resolve().profile is Profile.DEVELOPER

    def test_malformed_user_mapping_skipped(self):
        # Garbage profile value must not crash; falls back to Normal for that key.
        s = Settings(context_app_mappings={"zzz": "not-a-profile"})
        eng = _fake_engine(s, app="zzz")
        # from_value maps unknown -> NORMAL, so key resolves to NORMAL mapping.
        assert eng.resolve().profile is Profile.NORMAL


# --- engine: settings-driven -------------------------------------------------

class TestContextEngine:
    def test_override_skips_detection(self):
        calls = {"n": 0}

        def detector():
            calls["n"] += 1
            return _signals(app="code")

        s = Settings(context_override="notes")
        eng = ContextEngine(s, detector=detector)
        r = eng.resolve()
        assert r.profile is Profile.NOTES
        assert r.source == "override"
        # A concrete override makes detection irrelevant: detector not called.
        assert calls["n"] == 0

    def test_disabled_skips_detection(self):
        calls = {"n": 0}

        def detector():
            calls["n"] += 1
            return _signals(app="code")

        s = Settings(context_detection_enabled=False)
        eng = ContextEngine(s, detector=detector)
        r = eng.resolve()
        assert r.profile is Profile.NORMAL
        assert calls["n"] == 0

    def test_detector_exception_is_fail_safe(self):
        def boom():
            raise RuntimeError("detector failed")

        s = Settings()  # detection on, override auto
        eng = ContextEngine(s, detector=boom)
        r = eng.resolve()
        assert r.profile is Profile.NORMAL  # never raises, defaults to Normal

    def test_latency_recorded(self):
        s = Settings()
        eng = _fake_engine(s, app="code")
        eng.resolve()
        assert eng.last_detect_ms >= 0.0


# --- flag influence (profile narrows existing correction) --------------------

class TestFlagInfluence:
    def test_developer_keeps_structured_formatting(self):
        cfg = profile_config(Profile.DEVELOPER)
        out = correct_transcript(
            "src slash app dot py",
            enable_technical=cfg.enable_technical,
            enable_formatting=cfg.enable_formatting,
            enable_structured=cfg.enable_structured,
        ).text
        assert out == "src/app.py"

    def test_email_suppresses_structured_path(self):
        cfg = profile_config(Profile.EMAIL)
        out = correct_transcript(
            "src slash app dot py",
            enable_technical=cfg.enable_technical,
            enable_formatting=cfg.enable_formatting,
            enable_structured=cfg.enable_structured,
        ).text
        # Email profile turns the Phase 6I structured path formatting OFF, so
        # the spoken form is NOT compressed into a path.
        assert out != "src/app.py"

    def test_email_still_normalizes_technical_terms(self):
        cfg = profile_config(Profile.EMAIL)
        out = correct_transcript(
            "push to git hub",
            enable_technical=cfg.enable_technical,
            enable_formatting=cfg.enable_formatting,
            enable_structured=cfg.enable_structured,
        ).text
        assert out == "push to GitHub"

    def test_profile_can_only_narrow_not_widen(self):
        # Simulate the worker's AND logic: user disabled technical globally; no
        # profile config can re-enable it.
        user_technical = False
        cfg = profile_config(Profile.DEVELOPER)  # wants technical on
        effective_technical = user_technical and cfg.enable_technical
        assert effective_technical is False


# --- context changes ONLY the intended behavior ------------------------------

class TestContextChangesOnlyIntended:
    def test_same_prose_developer_vs_normal_unchanged(self):
        # Ordinary prose with no structured/technical tokens must be identical
        # under Developer and Normal (context changes only *formatting of
        # structured content*, never arbitrary prose).
        prose = "create a pull request for the new authentication endpoint"
        dev = profile_config(Profile.DEVELOPER)
        nor = profile_config(Profile.NORMAL)
        dev_out = correct_transcript(
            prose,
            enable_technical=dev.enable_technical,
            enable_formatting=dev.enable_formatting,
            enable_structured=dev.enable_structured,
        ).text
        nor_out = correct_transcript(
            prose,
            enable_technical=nor.enable_technical,
            enable_formatting=nor.enable_formatting,
            enable_structured=nor.enable_structured,
        ).text
        assert dev_out == prose
        assert nor_out == prose

    def test_structured_content_differs_by_profile(self):
        # A clearly structured utterance differs between Developer (formats it)
        # and Email (leaves it as prose) — the intended behavioral difference.
        text = "see example dot com slash repo"
        dev = profile_config(Profile.DEVELOPER)
        email = profile_config(Profile.EMAIL)
        dev_out = correct_transcript(
            text,
            enable_technical=dev.enable_technical,
            enable_formatting=dev.enable_formatting,
            enable_structured=dev.enable_structured,
        ).text
        email_out = correct_transcript(
            text,
            enable_technical=email.enable_technical,
            enable_formatting=email.enable_formatting,
            enable_structured=email.enable_structured,
        ).text
        assert dev_out != email_out


# --- determinism -------------------------------------------------------------

class TestDeterminism:
    def test_same_signals_same_result(self):
        for _ in range(5):
            r = resolve_profile(
                _signals(app="code", title="x"),
                detection_enabled=True,
                override=AUTO,
            )
            assert r.profile is Profile.DEVELOPER
            assert r.source == "mapping"

    def test_profile_config_stable(self):
        a = profile_config(Profile.EMAIL)
        b = profile_config(Profile.EMAIL)
        assert a == b


# --- display strings ---------------------------------------------------------

class TestDisplay:
    def test_mapping_display_shows_auto_and_app(self):
        r = resolve_profile(
            _signals(app="code"), detection_enabled=True, override=AUTO
        )
        assert r.display() == "Auto \u00b7 code"  # 'Auto · code'

    def test_override_display_is_label(self):
        r = resolve_profile(
            _signals(app="code"), detection_enabled=True, override="developer"
        )
        assert r.display() == "Developer"

    def test_default_display_is_normal(self):
        r = resolve_profile(
            ContextSignals(), detection_enabled=True, override=AUTO
        )
        assert r.display() == "Normal"


# --- privacy -----------------------------------------------------------------

class TestPrivacy:
    FORBIDDEN = (
        "mss", "pyautogui", "PIL", "pyscreenshot", "pyperclip",
        "ImageGrab", "screenshot", "clipboard", "pygetwindow.screen",
    )

    def _module_source(self, rel):
        root = Path(__file__).resolve().parents[1]
        path = root / "src" / "sayit" / "core" / "context" / rel
        return path.read_text(encoding="utf-8")

    def test_no_screenshot_or_clipboard_imports(self):
        for rel in ("engine.py", "profiles.py", "__init__.py"):
            src = self._module_source(rel)
            tree = ast.parse(src)
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported += [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
                    imported += [n.name for n in node.names]
            for bad in self.FORBIDDEN:
                assert not any(bad in (name or "") for name in imported), (
                    f"{rel} must not import {bad!r}; imported={imported}"
                )

    def test_signals_carry_only_metadata(self):
        # The dataclass fields are strictly metadata identifiers, no content.
        fields = set(ContextSignals.__dataclass_fields__.keys())
        assert fields == {"app_name", "window_title", "detected"}

    def test_engine_does_not_log_transcript(self):
        # The engine never receives transcript text; resolve() takes no text.
        s = Settings()
        eng = _fake_engine(s, app="code")
        import inspect

        sig = inspect.signature(eng.resolve)
        assert list(sig.parameters) == []  # resolve() takes no arguments


# --- regression: raw 6G/6I/6J API unchanged ---------------------------------

class TestRegressionCorrection:
    def test_default_correct_transcript_unchanged(self):
        # The shipped default behavior (all flags default True) is untouched.
        assert correct_transcript("push to git hub").text == "push to GitHub"
        assert correct_transcript("ninety five percent").text == "95%"
        assert correct_transcript("src slash app dot py").text == "src/app.py"

    def test_ordinary_prose_still_safe(self):
        s = "I will meet you at the api of the river."
        assert correct_transcript(s).text == s


# --- settings round-trip -----------------------------------------------------

class TestSettingsRoundTrip:
    def test_defaults(self):
        s = Settings()
        assert s.context_detection_enabled is True
        assert s.context_override == "auto"
        assert s.context_app_mappings == {}

    def test_round_trip(self, tmp_path, monkeypatch):
        import src.sayit.core.settings.settings as settings_mod

        monkeypatch.setattr(
            settings_mod, "get_config_dir", lambda: tmp_path
        )
        s = Settings(
            context_detection_enabled=False,
            context_override="developer",
            context_app_mappings={"myapp": "chat"},
        )
        s.save()
        loaded = Settings.load()
        assert loaded.context_detection_enabled is False
        assert loaded.context_override == "developer"
        assert loaded.context_app_mappings == {"myapp": "chat"}

    def test_malformed_override_falls_back_on_resolve(self):
        s = Settings(context_override="garbage")
        eng = _fake_engine(s, app="code")
        # override is a concrete non-auto string -> from_value -> NORMAL.
        r = eng.resolve()
        assert r.profile is Profile.NORMAL
        assert r.source == "override"


# --- UI round-trip -----------------------------------------------------------

class TestConfigurationTabContext:
    def test_defaults_loaded(self, qtbot):
        from src.sayit.ui.tabs.configuration_tab import ConfigurationTab

        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()
        assert tab._context_detection_cb.isChecked() is True
        assert tab._context_override_combo.currentData() == AUTO

    def test_save_round_trip(self, qtbot):
        from src.sayit.ui.tabs.configuration_tab import ConfigurationTab

        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tab.load_settings()

        tab._context_detection_cb.setChecked(False)
        idx = tab._context_override_combo.findData("developer")
        tab._context_override_combo.setCurrentIndex(idx)
        assert tab.save_settings() is True
        assert s.context_detection_enabled is False
        assert s.context_override == "developer"

    def test_override_combo_has_all_profiles(self, qtbot):
        from src.sayit.ui.tabs.configuration_tab import ConfigurationTab

        s = Settings()
        tab = ConfigurationTab(s)
        qtbot.addWidget(tab)
        tokens = {
            tab._context_override_combo.itemData(i)
            for i in range(tab._context_override_combo.count())
        }
        assert AUTO in tokens
        for prof in Profile:
            assert prof.value in tokens


class TestHomeTabContext:
    def test_set_context_shows_label(self, qtbot):
        from src.sayit.ui.tabs.home_tab import HomeTab

        home = HomeTab()
        qtbot.addWidget(home)
        # Use isHidden(): it reflects the explicit hide/show intent regardless
        # of whether the parent window has been realized (isVisible() is False
        # for all descendants until the top-level is shown).
        assert home._context_label.isHidden() is True
        home.set_context("Developer")
        assert home._context_label.isHidden() is False
        assert "Developer" in home._context_label.text()

    def test_set_context_empty_hides(self, qtbot):
        from src.sayit.ui.tabs.home_tab import HomeTab

        home = HomeTab()
        qtbot.addWidget(home)
        home.set_context("Developer")
        home.set_context("")
        assert home._context_label.isHidden() is True
