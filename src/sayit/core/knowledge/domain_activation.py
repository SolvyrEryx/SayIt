"""Domain-aware knowledge activation.

Extends (does NOT replace) the existing 9C index / 9D domain packs / 9E entities
/ 9F ranker so SayIt's technical coverage can be *organized and prioritized by
domain* instead of becoming one huge noisy global dictionary. Three jobs:

1. **GLOBAL CORE + DOMAINS.** The existing ``DOMAIN_PACKS`` (9D) and
   ``ENTITY_PACKS`` (9E) are grouped into a GLOBAL CORE (always active, widely
   used terms) plus optional DOMAIN groups (web / python / ai_ml / data_sql /
   devops_cloud / cybersecurity). Grouping is a *view* over the existing packs;
   no term is duplicated and no new knowledge system is created.

2. **ACTIVATION + PRECEDENCE.** ``DomainActivation`` resolves which domains are
   active for a given context, honoring the required priority model:
       EXPLICIT USER DOMAIN  >  CURRENT CONTEXT  >  DOMAIN-PACK RELEVANCE  >  CORE
   Passive context never overrides an explicit user choice. Core is always on.

3. **BOUNDED DOMAIN PRIOR.** ``domain_relevance(domain, active)`` returns a
   bounded [0..1] prior the 9F ranker consumes as *one feature among many*. A
   domain prior can only *raise* a candidate's score within bounds; it can never
   bypass the accept threshold, margin, ambiguity, or ordinary-language gates.
   Safety stays dominant.

Everything is local, inert, deterministic data. No network, no learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .domain_packs import DOMAIN_PACKS, pack_terms
from .entities import ENTITY_PACKS, entity_terms
from .index import KnowledgeIndex
from .models import Domain, KnowledgeTerm

ACTIVATION_SCHEMA_VERSION = "di.1"

# ---------------------------------------------------------------------------
# GLOBAL CORE + named domains. Keys are the user-facing domains from the spec.
# Each maps to existing 9D domain-pack names and 9E entity-group names. The
# GLOBAL CORE is always active: the small set of widely-used terms + the
# conservative ambiguous-entity packs that must always be present so the ranker
# can *abstain* on them (removing them would make the system less safe, not more).
# ---------------------------------------------------------------------------

# User-facing domain -> (9D pack names, 9E entity group names).
DOMAIN_GROUPS: Dict[str, Dict[str, List[str]]] = {
    "web":            {"packs": ["web"], "entities": []},
    "python":         {"packs": ["python"], "entities": []},
    "ai_ml":          {"packs": ["ai_ml"], "entities": ["organizations"]},
    "data_sql":       {"packs": ["databases", "data_engineering"], "entities": []},
    "devops_cloud":   {"packs": ["devops", "cloud"], "entities": ["products"]},
    "cybersecurity":  {"packs": ["security"], "entities": ["standards"]},
    "academic":       {"packs": ["academic"], "entities": []},
    # Domain-coverage expansion (science/engineering packs; opt-in).
    "aerospace":      {"packs": [], "science": ["aerospace_engineering"], "entities": []},
    "control_systems": {"packs": [], "science": ["control_systems"], "entities": []},
    "chemistry":      {"packs": [], "science": ["chemistry_biochem"], "entities": []},
    "electronics":    {"packs": [], "science": ["electronics"], "entities": []},
    "mathematics":    {"packs": [], "science": ["mathematics"], "entities": []},
}

# GLOBAL CORE packs/entities — always active.
CORE_PACKS: List[str] = ["web"]            # FastAPI/React/etc. are broadly useful
CORE_ENTITY_GROUPS: List[str] = [
    "organizations", "products", "languages_ambiguous", "standards", "locations",
]

# Context -> domains that a context *passively* suggests (a prior, not a choice).
# Developer-ish contexts suggest the technical domains; ordinary contexts suggest
# none (so technical priors are strongly downweighted there).
CONTEXT_SUGGESTED_DOMAINS: Dict[str, List[str]] = {
    "developer": ["web", "python", "ai_ml", "data_sql", "devops_cloud", "cybersecurity"],
    "prompt":    ["web", "python", "ai_ml"],
    "notes":     ["web", "python"],
    "normal":    [],
    "email":     [],
    "chat":      [],
}
# Science/engineering domains are OPT-IN ONLY: no context passively suggests
# them (a developer talking is not evidence of aerospace/chemistry speech). They
# activate only when the user explicitly enables them.

# Bounded domain-relevance prior values (consumed by the ranker as ONE feature).
_REL_EXPLICIT = 1.0    # user explicitly enabled this domain
_REL_CONTEXT = 0.8     # context suggests it
_REL_CORE = 0.6        # core / fallback
_REL_INACTIVE = 0.3    # domain exists but is not active in this context


def all_domain_names() -> List[str]:
    return list(DOMAIN_GROUPS)


@dataclass
class DomainActivation:
    """Resolves active domains + a bounded per-domain relevance prior.

    ``user_enabled`` are domains the user explicitly turned on (strongest).
    ``user_disabled`` are domains the user explicitly turned off (never active,
    even if a context suggests them — explicit user choice wins). Core is always
    active and cannot be disabled (it carries the conservative ambiguous entities
    the ranker needs to abstain safely)."""

    user_enabled: Set[str] = field(default_factory=set)
    user_disabled: Set[str] = field(default_factory=set)

    @classmethod
    def from_settings(cls, enabled: Optional[List[str]], disabled: Optional[List[str]]) -> "DomainActivation":
        valid = set(DOMAIN_GROUPS)
        return cls(
            user_enabled={d for d in (enabled or []) if d in valid},
            user_disabled={d for d in (disabled or []) if d in valid},
        )

    def active_domains(self, context: Optional[str]) -> Set[str]:
        """Domains active for this context, honoring precedence.
        explicit-enabled ∪ (context-suggested \\ explicit-disabled)."""
        ctx = (context or "normal").lower()
        suggested = set(CONTEXT_SUGGESTED_DOMAINS.get(ctx, []))
        active = set(self.user_enabled) | (suggested - self.user_disabled)
        # Explicit disable always wins (even over an enable? no — enable is the
        # user's choice too; but disabling a domain the user also enabled is
        # contradictory input: treat explicit disable as the stricter signal).
        active -= self.user_disabled
        return active

    def domain_relevance(self, domain: str, context: Optional[str]) -> float:
        """Bounded [0..1] relevance prior for a candidate's *domain* given the
        active configuration. Used by the ranker as a single bounded feature."""
        # Map a term's low-level Domain (developer/ai_ml/...) to user-facing groups.
        groups = _domain_to_groups(domain)
        if not groups:
            return _REL_CORE
        ctx = (context or "normal").lower()
        suggested = set(CONTEXT_SUGGESTED_DOMAINS.get(ctx, []))
        best = _REL_INACTIVE
        for g in groups:
            if g in self.user_disabled:
                continue
            if g in self.user_enabled:
                best = max(best, _REL_EXPLICIT)
            elif g in suggested:
                best = max(best, _REL_CONTEXT)
            else:
                best = max(best, _REL_CORE if g in CORE_PACKS else _REL_INACTIVE)
        return best


# low-level Domain constant -> user-facing group names.
_LOWLEVEL_TO_GROUP: Dict[str, List[str]] = {
    Domain.DEVELOPER: ["web", "python", "data_sql"],
    Domain.AI_ML: ["ai_ml"],
    Domain.DATA_SCIENCE: ["data_sql"],
    Domain.DEVOPS: ["devops_cloud"],
    Domain.SECURITY: ["cybersecurity"],
    Domain.AEROSPACE: ["aerospace"],
    Domain.CONTROL: ["control_systems"],
    Domain.CHEMISTRY: ["chemistry"],
    Domain.ELECTRONICS: ["electronics"],
    Domain.MATHEMATICS: ["mathematics"],
    Domain.GENERAL: [],
}


def _domain_to_groups(domain: str) -> List[str]:
    return _LOWLEVEL_TO_GROUP.get(domain, [])


def active_terms(activation: DomainActivation, context: Optional[str]) -> List[KnowledgeTerm]:
    """Build the active term set: GLOBAL CORE + active domain groups.
    Deterministic + de-duplicated by canonical."""
    active = activation.active_domains(context)
    pack_names: List[str] = list(CORE_PACKS)
    entity_groups: List[str] = list(CORE_ENTITY_GROUPS)
    science_names: List[str] = []
    for g in sorted(active):
        grp = DOMAIN_GROUPS.get(g, {})
        pack_names.extend(grp.get("packs", []))
        entity_groups.extend(grp.get("entities", []))
        science_names.extend(grp.get("science", []))
    # De-dup names preserving determinism.
    pack_names = [p for p in dict.fromkeys(pack_names) if p in DOMAIN_PACKS]
    entity_groups = [e for e in dict.fromkeys(entity_groups) if e in ENTITY_PACKS]
    terms = pack_terms(pack_names) + entity_terms(entity_groups)
    if science_names:
        from .science_packs import SCIENCE_PACKS, science_pack_terms
        science_names = [s for s in dict.fromkeys(science_names) if s in SCIENCE_PACKS]
        terms = terms + science_pack_terms(science_names)
    # De-dup by canonical (first wins; deterministic by construction order).
    out: Dict[str, KnowledgeTerm] = {}
    for t in terms:
        out.setdefault(t.canonical, t)
    return list(out.values())


def build_active_index(activation: DomainActivation, context: Optional[str]) -> KnowledgeIndex:
    """A compact KnowledgeIndex over just the active (core + active-domain) terms."""
    return KnowledgeIndex(active_terms(activation, context))
