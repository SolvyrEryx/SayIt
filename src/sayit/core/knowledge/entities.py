"""Phase 9E — proper names + rare entity intelligence (conservative).

Adds a small, local, curated layer of proper-name / rare entities (PERSON,
ORGANIZATION, PRODUCT, PROJECT, LOCATION, STANDARD, PROTOCOL, TECHNICAL_ENTITY)
that are hard for ordinary dictionaries. The overriding principle is
CONSERVATISM: entities that collide with ordinary words or have multiple
plausible meanings (Apple, Jordan, Amazon, Go, Swift, Rust) are flagged
``AMB_PROPER``/``AMB_ORDINARY`` so the ranker requires stronger evidence and
otherwise abstains (LEAVE_UNCHANGED / AMBIGUOUS).

Local, inert data. No runtime network. OSMNames and similar gazetteers are
documented as POTENTIAL build-time sources in the manifest; this phase ships a
bounded curated real subset rather than importing a world gazetteer (which
would create candidate explosion and ordinary-word collisions). Canonical forms
are official/attested display forms, not invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..knowledge.models import Domain, KnowledgeTerm
from .domain_packs import AMB_NONE, AMB_ORDINARY, AMB_PROPER, CONF_CURATED, CONF_OFFICIAL

ENTITY_SCHEMA_VERSION = "9e.1"

# Entity types.
PERSON = "person"
ORGANIZATION = "organization"
PRODUCT = "product"
PROJECT = "project"
LOCATION = "location"
STANDARD = "standard"
PROTOCOL = "protocol"
TECHNICAL_ENTITY = "technical_entity"


@dataclass
class Entity:
    spoken_form: str
    canonical_form: str
    entity_type: str
    aliases: Tuple[str, ...] = ()
    domain: str = Domain.GENERAL
    source: str = "curated"
    source_confidence: float = CONF_CURATED
    canonical_confidence: float = CONF_OFFICIAL
    ambiguity_class: str = AMB_NONE
    locale: str = ""
    enabled: bool = True
    version: str = ENTITY_SCHEMA_VERSION

    def to_knowledge_term(self) -> KnowledgeTerm:
        variants = tuple(dict.fromkeys([self.spoken_form, *self.aliases]))
        return KnowledgeTerm(
            canonical=self.canonical_form, spoken_variants=variants,
            category=self.entity_type, domain=self.domain, source=self.source,
            relevance=round(0.5 * self.source_confidence + 0.5 * self.canonical_confidence, 3),
            metadata={"canonical_confidence": str(self.canonical_confidence),
                      "ambiguity_class": self.ambiguity_class,
                      "entity_type": self.entity_type,
                      "locale": self.locale, "pack_version": self.version})


def _e(spoken, canonical, etype, aliases=(), amb=AMB_NONE, domain=Domain.GENERAL,
       locale="", cconf=CONF_OFFICIAL):
    return Entity(spoken_form=spoken, canonical_form=canonical, entity_type=etype,
                  aliases=aliases, domain=domain, ambiguity_class=amb, locale=locale,
                  canonical_confidence=cconf)


# Curated real entities. Highly ambiguous ones (Apple/Jordan/Amazon/Go/Swift)
# are deliberately flagged so the ranker abstains without strong evidence.
_ORGANIZATIONS = [
    _e("open ai", "OpenAI", ORGANIZATION, ("openai",), AMB_NONE, Domain.AI_ML),
    _e("anthropic", "Anthropic", ORGANIZATION),
    _e("hugging face", "Hugging Face", ORGANIZATION, ("huggingface",), AMB_NONE, Domain.AI_ML),
    _e("nvidia", "NVIDIA", ORGANIZATION, ("en vidia",)),
    _e("amazon", "Amazon", ORGANIZATION, (), AMB_PROPER),       # also river/ordinary
    _e("apple", "Apple", ORGANIZATION, (), AMB_ORDINARY),       # also fruit
    _e("microsoft", "Microsoft", ORGANIZATION, ("micro soft",)),
]

_PRODUCTS = [
    _e("git hub", "GitHub", PRODUCT, ("github",), AMB_NONE, Domain.DEVELOPER),
    _e("git lab", "GitLab", PRODUCT, ("gitlab",), AMB_NONE, Domain.DEVELOPER),
    _e("vs code", "VS Code", PRODUCT, ("vscode", "visual studio code"), AMB_NONE, Domain.DEVELOPER),
    _e("kubernetes", "Kubernetes", PRODUCT, ("kube netes",), AMB_NONE, Domain.DEVOPS),
]

_LANGUAGES_AMBIG = [
    # Programming languages whose names are ordinary words -> conservative.
    _e("go", "Go", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),
    _e("swift", "Swift", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),
    _e("rust", "Rust", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),
    _e("python", "Python", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),
    _e("java", "Java", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),  # also coffee
    _e("ruby", "Ruby", TECHNICAL_ENTITY, (), AMB_ORDINARY, Domain.DEVELOPER),  # also gem/name
    _e("scala", "Scala", TECHNICAL_ENTITY, (), AMB_PROPER, Domain.DEVELOPER),
]

_STANDARDS = [
    _e("web auth n", "WebAuthn", STANDARD, ("webauthn",), AMB_NONE, Domain.SECURITY),
    _e("open id connect", "OpenID Connect", STANDARD, ("openid connect",), AMB_NONE, Domain.SECURITY),
    _e("http two", "HTTP/2", PROTOCOL, ("http 2", "h t t p two")),
    _e("quic", "QUIC", PROTOCOL, ("quick",), AMB_ORDINARY),
]

_LOCATIONS = [
    # Bounded curated real locations (OSMNames would be the build-time source).
    _e("san francisco", "San Francisco", LOCATION, (), AMB_NONE, Domain.GENERAL, "US"),
    _e("bengaluru", "Bengaluru", LOCATION, ("bangalore",), AMB_NONE, Domain.GENERAL, "IN"),
    _e("reykjavik", "Reykjavík", LOCATION, ("reykjavik",), AMB_NONE, Domain.GENERAL, "IS"),
    _e("jordan", "Jordan", LOCATION, (), AMB_PROPER, Domain.GENERAL, "JO"),  # also a name
]

ENTITY_PACKS: Dict[str, List[Entity]] = {
    "organizations": _ORGANIZATIONS,
    "products": _PRODUCTS,
    "languages_ambiguous": _LANGUAGES_AMBIG,
    "standards": _STANDARDS,
    "locations": _LOCATIONS,
}


def entity_terms(groups: List[str] | None = None) -> List[KnowledgeTerm]:
    names = groups if groups is not None else list(ENTITY_PACKS)
    out: List[KnowledgeTerm] = []
    for name in names:
        for ent in ENTITY_PACKS.get(name, []):
            if ent.enabled:
                out.append(ent.to_knowledge_term())
    return out


def entity_stats() -> Dict[str, dict]:
    stats = {}
    for name, ents in ENTITY_PACKS.items():
        stats[name] = {
            "count": len(ents),
            "ambiguous": sum(1 for e in ents if e.ambiguity_class != AMB_NONE),
            "types": sorted({e.entity_type for e in ents}),
        }
    return stats
