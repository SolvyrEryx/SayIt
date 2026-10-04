"""Domain-coverage expansion tests: science packs, new-domain registration,
settings fields, UI selector round-trip, and leakage boundary.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sayit.core.knowledge.science_packs import (
    SCIENCE_PACKS, science_pack_terms, science_pack_stats, all_science_terms_lower,
)
from sayit.core.knowledge.domain_activation import (
    DomainActivation, DOMAIN_GROUPS, all_domain_names, active_terms,
    CONTEXT_SUGGESTED_DOMAINS,
)
from sayit.core.knowledge.models import Domain
from sayit.core.settings import Settings

SCIENCE_DOMAINS = ["aerospace", "control_systems", "chemistry", "electronics", "mathematics"]

# The held-out TIE target terms (lowercased) that MUST NOT be copied verbatim as
# the *reason* a pack exists. HPLC/LQR/ELISA are universal acronyms allowed with
# justification; the overfit-prone specifics must be ABSENT.
FORBIDDEN_HELDOUT = {"soft-in-plane", "stiff-in-plane", "cad", "pre-multiply",
                     "pre-multiplying", "so.basically", "cpg", "iit"}


class TestSciencePacks:
    def test_packs_parse(self):
        for name in SCIENCE_PACKS:
            terms = science_pack_terms([name])
            assert terms
            for t in terms:
                assert t.canonical.strip() and t.is_valid()

    def test_every_term_has_provenance(self):
        for name in SCIENCE_PACKS:
            for t in science_pack_terms([name]):
                assert t.metadata.get("provenance"), f"{t.canonical} missing provenance"

    def test_no_forbidden_heldout_overfit_terms(self):
        forms = all_science_terms_lower()
        leaked = forms & FORBIDDEN_HELDOUT
        assert leaked == set(), f"overfit/leaked held-out terms present: {leaked}"

    def test_packs_are_bounded(self):
        for name, terms in SCIENCE_PACKS.items():
            assert len(terms) <= 30, f"{name} too large ({len(terms)})"

    def test_low_level_domains_assigned(self):
        doms = {t.domain for t in science_pack_terms(["aerospace_engineering"])}
        assert Domain.AEROSPACE in doms


class TestNewDomainRegistration:
    def test_science_domains_registered(self):
        for d in SCIENCE_DOMAINS:
            assert d in DOMAIN_GROUPS
            assert d in all_domain_names()

    def test_science_domains_not_context_suggested(self):
        # Opt-in only: no context passively activates a science domain.
        for ctx, suggested in CONTEXT_SUGGESTED_DOMAINS.items():
            for d in SCIENCE_DOMAINS:
                assert d not in suggested

    def test_enabling_science_domain_adds_terms(self):
        base = DomainActivation.from_settings([], [])
        with_chem = DomainActivation.from_settings(["chemistry"], [])
        n_base = len(active_terms(base, "developer"))
        n_chem = len(active_terms(with_chem, "developer"))
        assert n_chem > n_base

    def test_science_domain_relevance_bounded(self):
        a = DomainActivation.from_settings(["chemistry"], [])
        r = a.domain_relevance(Domain.CHEMISTRY, "developer")
        assert 0.0 <= r <= 1.0 and r == 1.0  # explicitly enabled


class TestSettingsFields:
    def test_domain_settings_defaults(self):
        s = Settings()
        assert s.intelligence_domain_aware is False
        assert s.enabled_domains == []
        assert s.disabled_domains == []

    def test_domain_settings_roundtrip(self):
        s = Settings(enabled_domains=["chemistry", "aerospace"],
                     intelligence_domain_aware=True)
        d = s.model_dump()
        s2 = Settings(**d)
        assert s2.enabled_domains == ["chemistry", "aerospace"]
        assert s2.intelligence_domain_aware is True


class TestUIDomainSelector:
    def _tab(self):
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        from sayit.ui.tabs.configuration_tab import ConfigurationTab
        app = QApplication.instance() or QApplication([])
        return ConfigurationTab(Settings(enabled_domains=["chemistry"])), app

    def test_selector_lists_all_domains(self):
        tab, _ = self._tab()
        for d in all_domain_names():
            assert d in tab._domain_checks

    def test_load_reflects_settings(self):
        tab, _ = self._tab()
        tab.load_settings()
        assert tab._domain_checks["chemistry"].isChecked()
        assert not tab._domain_checks["aerospace"].isChecked()

    def test_save_writes_enabled_domains(self):
        tab, _ = self._tab()
        tab.load_settings()
        tab._domain_checks["aerospace"].setChecked(True)
        assert tab.save_settings()
        assert set(tab._settings.enabled_domains) == {"chemistry", "aerospace"}

    def test_reset_clears_domains(self):
        tab, _ = self._tab()
        tab.load_settings()
        tab._reset_domains()
        assert not any(cb.isChecked() for cb in tab._domain_checks.values())


class TestNoLeakageInActive:
    def test_active_science_terms_exclude_forbidden(self):
        a = DomainActivation.from_settings(SCIENCE_DOMAINS, [])
        forms = {t.canonical.lower() for t in active_terms(a, "developer")}
        assert forms & FORBIDDEN_HELDOUT == set()
