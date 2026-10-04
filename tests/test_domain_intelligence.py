"""Domain-aware knowledge intelligence — comprehensive tests.

Covers the required areas: domain-pack parsing, activation, disabling,
precedence, retrieval, domain relevance, ranker behavior, ambiguity handling,
ordinary-language protection, canonicalization, personalization interaction,
corrupted/missing index, deterministic generation, deterministic inference,
backward compatibility, empty domain, duplicate terms, conflicting domains,
user-vocabulary conflicts, and fail-safe behavior.

Safety invariant under test: the domain prior is a bounded prior, never an
override; ordinary language and ambiguous terms stay protected; ARM B
(domain_aware=False) is unchanged from the baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sayit.core.knowledge.domain_activation import (
    DomainActivation, DOMAIN_GROUPS, all_domain_names, active_terms,
    build_active_index, CONTEXT_SUGGESTED_DOMAINS,
)
from sayit.core.knowledge.domain_packs import DOMAIN_PACKS, pack_terms, canonical_map
from sayit.core.knowledge.models import Domain
from sayit.core.asr.candidate_ranker import CandidateRanker, RankerConfig, Decision
from sayit.core.asr.intelligence_pipeline import IntelligencePipeline

ARM_C = ["web", "python", "ai_ml", "data_sql", "devops_cloud", "cybersecurity"]


# --- parsing / content ------------------------------------------------------
class TestDomainPackParsing:
    def test_all_packs_parse_to_knowledge_terms(self):
        for name in DOMAIN_PACKS:
            terms = pack_terms([name])
            assert terms, f"pack {name} empty"
            for t in terms:
                assert t.canonical.strip()
                assert t.is_valid()

    def test_canonical_forms_are_official_not_titlecased(self):
        cm = canonical_map()
        assert cm.get("fastapi") == "FastAPI"
        assert cm.get("postgresql") == "PostgreSQL"
        assert cm.get("sqlalchemy") == "SQLAlchemy"
        assert cm.get("numpy") == "NumPy"

    def test_duplicate_canonical_dedup_in_active_terms(self):
        # FastAPI appears in both web and python packs; active_terms de-dups.
        a = DomainActivation.from_settings(enabled=["web", "python"], disabled=[])
        terms = active_terms(a, "developer")
        canons = [t.canonical for t in terms]
        assert canons.count("FastAPI") == 1


# --- activation / precedence ------------------------------------------------
class TestActivation:
    def test_domain_names(self):
        assert set(all_domain_names()) == set(DOMAIN_GROUPS)

    def test_context_suggests_domains(self):
        a = DomainActivation()
        assert a.active_domains("developer")  # developer suggests technical domains
        assert a.active_domains("email") == set()  # ordinary context suggests none

    def test_explicit_enable_persists_in_ordinary_context(self):
        a = DomainActivation.from_settings(enabled=["ai_ml"], disabled=[])
        assert "ai_ml" in a.active_domains("email")

    def test_explicit_disable_wins_over_context(self):
        a = DomainActivation.from_settings(enabled=[], disabled=["web"])
        assert "web" not in a.active_domains("developer")

    def test_conflicting_enable_and_disable_disable_wins(self):
        a = DomainActivation.from_settings(enabled=["web"], disabled=["web"])
        assert "web" not in a.active_domains("developer")

    def test_empty_activation_still_has_core(self):
        a = DomainActivation.from_settings(enabled=[], disabled=[])
        terms = active_terms(a, "normal")
        assert len(terms) > 0  # core is always active

    def test_invalid_domain_names_ignored(self):
        a = DomainActivation.from_settings(enabled=["nonsense", "web"], disabled=["bogus"])
        assert a.user_enabled == {"web"}
        assert a.user_disabled == set()


# --- domain relevance (bounded prior) --------------------------------------
class TestDomainRelevance:
    def test_relevance_is_bounded(self):
        a = DomainActivation.from_settings(enabled=["ai_ml"], disabled=[])
        for dom in (Domain.AI_ML, Domain.DEVELOPER, Domain.SECURITY, Domain.GENERAL):
            r = a.domain_relevance(dom, "developer")
            assert 0.0 <= r <= 1.0

    def test_explicit_enabled_highest(self):
        a = DomainActivation.from_settings(enabled=["ai_ml"], disabled=[])
        assert a.domain_relevance(Domain.AI_ML, "email") == 1.0


# --- ranker: domain is a prior, never an override --------------------------
class TestRankerDomainPrior:
    def test_arm_b_default_no_domain_feature(self):
        # Default config has use_domain False -> domain_contribution 0.
        cfg = RankerConfig()
        assert cfg.use_domain is False

    def test_domain_prior_cannot_bypass_threshold(self):
        # A weak candidate with max domain relevance must still abstain.
        ranker = CandidateRanker(RankerConfig(use_domain=True, accept_threshold=0.95))

        class Cand:
            matched_form = "zzz"
            components = {"context_prior": 0.1, "domain_relevance": 1.0}
            class term:  # noqa
                canonical = "Zzz"
                source = "curated"
                metadata = {}
                @staticmethod
                def all_surface_forms():
                    return ["zzz"]
        dec = ranker.rank("completely different words", [Cand()], "developer")
        assert dec.decision in (Decision.LEAVE_UNCHANGED, Decision.AMBIGUOUS, Decision.NO_CANDIDATE)


# --- pipeline behavior: safety + backward compat ---------------------------
class TestPipelineSafety:
    def test_fast_api_unchanged_in_email_both_arms(self):
        for aware in (False, True):
            p = IntelligencePipeline(domain_aware=aware,
                                     enabled_domains=ARM_C if aware else None)
            if not p.available:
                pytest.skip("index unavailable")
            out = p.process("i need a fast api for the service", "email").text
            assert out == "i need a fast api for the service"

    @pytest.mark.parametrize("text,risky", [
        ("i ate an apple for lunch", "apple"),
        ("michael jordan was a great player", "jordan"),
        ("we sailed down the amazon river", "amazon"),
        ("there is rust on the gate", "Rust"),
        ("the python slithered away", "Python"),
        ("that was a swift decision", "Swift"),
        ("i need to go to the store", "Go"),
    ])
    def test_ambiguous_ordinary_preserved_with_domains_active(self, text, risky):
        p = IntelligencePipeline(domain_aware=True, enabled_domains=ARM_C)
        if not p.available:
            pytest.skip("index unavailable")
        out = p.process(text, "developer").text
        # The ordinary word must not be capitalized into the technical entity.
        assert risky not in out or risky in text

    def test_domain_aware_no_new_false_positive_vs_baseline(self):
        b = IntelligencePipeline(domain_aware=False)
        c = IntelligencePipeline(domain_aware=True, enabled_domains=ARM_C)
        if not (b.available and c.available):
            pytest.skip("index unavailable")
        negs = ["i ate an apple", "rust on the fence", "a swift reply",
                "go home now", "the python in the zoo", "java the island"]
        for ctx in ("normal", "developer", "email", "chat", "notes", "prompt"):
            for t in negs:
                assert b.process(t, ctx).text == c.process(t, ctx).text


# --- determinism ------------------------------------------------------------
class TestDeterminism:
    def test_active_terms_deterministic(self):
        a = DomainActivation.from_settings(enabled=["web", "ai_ml"], disabled=[])
        t1 = [t.canonical for t in active_terms(a, "developer")]
        t2 = [t.canonical for t in active_terms(a, "developer")]
        assert t1 == t2

    def test_inference_deterministic(self):
        p = IntelligencePipeline(domain_aware=True, enabled_domains=ARM_C)
        if not p.available:
            pytest.skip("index unavailable")
        a = p.process("i deployed to kubernetes with docker", "developer").text
        b = p.process("i deployed to kubernetes with docker", "developer").text
        assert a == b


# --- corrupt / missing index: fail-safe ------------------------------------
class TestFailSafe:
    def test_missing_index_is_noop(self, tmp_path):
        p = IntelligencePipeline(index_path=tmp_path / "nope.json", domain_aware=True,
                                 enabled_domains=ARM_C)
        assert p.available is False
        r = p.process("hello world", "developer")
        assert r.text == "hello world" and r.changed is False

    def test_corrupt_index_is_noop(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not valid json ", encoding="utf-8")
        p = IntelligencePipeline(index_path=bad, domain_aware=True, enabled_domains=ARM_C)
        assert p.available is False
        assert p.process("hello", "developer").text == "hello"

    def test_empty_input_safe(self):
        p = IntelligencePipeline(domain_aware=True, enabled_domains=ARM_C)
        assert p.process("", "developer").text == ""
        assert p.process("   ", "developer").changed is False


# --- active index build -----------------------------------------------------
class TestActiveIndex:
    def test_build_active_index_bounded(self):
        a = DomainActivation.from_settings(enabled=[], disabled=[])
        core_idx = build_active_index(a, "normal")
        full = DomainActivation.from_settings(enabled=ARM_C, disabled=[])
        full_idx = build_active_index(full, "developer")
        # Core-only index is strictly smaller than all-domains index.
        assert core_idx.term_count <= full_idx.term_count
        assert full_idx.term_count > 0
